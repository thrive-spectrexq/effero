"""Real-time streaming video ingestion loop and frame queue management."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Frame:
    """Video frame container holding pixel data and capture metadata."""

    data: np.ndarray
    timestamp: float = field(default_factory=time.time)
    frame_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class FrameQueue:
    """Thread-safe frame queue with bounded latency and drop-oldest eviction policy."""

    def __init__(self, maxsize: int = 30, drop_oldest: bool = True) -> None:
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self.maxsize = maxsize
        self.drop_oldest = drop_oldest

        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._queue: deque[Frame] = deque()

        self._frames_ingested: int = 0
        self._frames_dropped: int = 0
        self._timestamps: deque[float] = deque(maxlen=60)

    @property
    def frames_ingested(self) -> int:
        with self._lock:
            return self._frames_ingested

    @property
    def frames_dropped(self) -> int:
        with self._lock:
            return self._frames_dropped

    @property
    def queue_depth(self) -> int:
        with self._lock:
            return len(self._queue)

    @property
    def drop_rate(self) -> float:
        with self._lock:
            if self._frames_ingested == 0:
                return 0.0
            return self._frames_dropped / self._frames_ingested

    @property
    def actual_fps(self) -> float:
        with self._lock:
            if len(self._timestamps) < 2:
                return 0.0
            duration = self._timestamps[-1] - self._timestamps[0]
            if duration <= 0:
                return 0.0
            return (len(self._timestamps) - 1) / duration

    def put(self, frame: np.ndarray | Frame, timestamp: float | None = None) -> bool:
        """Put a frame into the queue.

        If the queue is full and drop_oldest is True, the oldest frame is dropped
        to maintain bounded latency for real-time perception.
        """
        ts = timestamp if timestamp is not None else time.time()
        if isinstance(frame, np.ndarray):
            frame_obj = Frame(data=frame, timestamp=ts)
        else:
            frame_obj = frame

        with self._lock:
            self._timestamps.append(ts)
            if len(self._queue) >= self.maxsize:
                if self.drop_oldest:
                    self._queue.popleft()
                    self._frames_dropped += 1
                    self._queue.append(frame_obj)
                    self._frames_ingested += 1
                    self._condition.notify_all()
                    return True
                else:
                    self._frames_dropped += 1
                    return False
            else:
                self._queue.append(frame_obj)
                self._frames_ingested += 1
                self._condition.notify_all()
                return True

    def get(self, timeout: float | None = None) -> tuple[np.ndarray, float] | None:
        """Pop the oldest frame from the queue, blocking up to timeout seconds."""
        with self._condition:
            if len(self._queue) == 0:
                if timeout is not None and timeout <= 0:
                    return None
                notified = self._condition.wait(timeout=timeout)
                if not notified and len(self._queue) == 0:
                    return None
            if len(self._queue) == 0:
                return None
            frame = self._queue.popleft()
            return frame.data, frame.timestamp

    def get_nowait(self) -> tuple[np.ndarray, float] | None:
        """Pop the oldest frame immediately without blocking."""
        return self.get(timeout=0.0)

    def get_latest(self) -> np.ndarray | None:
        """Retrieve the most recently ingested frame data without popping it."""
        with self._lock:
            if not self._queue:
                return None
            return self._queue[-1].data

    def get_latest_frame(self) -> tuple[np.ndarray, float] | None:
        """Retrieve the most recently ingested frame (data, timestamp) without popping it."""
        with self._lock:
            if not self._queue:
                return None
            return self._queue[-1].data, self._queue[-1].timestamp

    async def read_frame(self, timeout: float | None = 1.0) -> np.ndarray | None:
        """Asynchronously await and read the next available frame from the queue."""
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, self.get, timeout)
        if res is None:
            return None
        return res[0]

    def get_stats(self) -> dict[str, Any]:
        """Return real-time queue ingestion and drop statistics."""
        with self._lock:
            return {
                "frames_ingested": self._frames_ingested,
                "frames_dropped": self._frames_dropped,
                "actual_fps": round(self.actual_fps, 2),
                "queue_depth": len(self._queue),
                "drop_rate": round(self.drop_rate, 4),
            }

    def clear(self) -> None:
        """Clear all frames from the queue."""
        with self._lock:
            self._queue.clear()


class SyntheticFrameGenerator:
    """Generates synthetic test pattern video frames for environments without camera/RTSP."""

    def __init__(self, width: int = 640, height: int = 480) -> None:
        self.width = width
        self.height = height

    def generate(self, frame_idx: int) -> np.ndarray:
        """Generate a dynamic RGB test pattern frame."""
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # Draw 6 color bars
        bar_width = max(1, self.width // 6)
        colors = [
            [220, 20, 60],  # Red
            [34, 139, 34],  # Green
            [30, 144, 255],  # Blue
            [255, 215, 0],  # Yellow
            [148, 0, 211],  # Violet
            [255, 140, 0],  # Orange
        ]
        for i, col in enumerate(colors):
            start_x = i * bar_width
            end_x = (i + 1) * bar_width if i < len(colors) - 1 else self.width
            frame[:, start_x:end_x] = col

        # Draw dynamic moving scanline to ensure temporal variance
        scan_y = int((frame_idx * 5) % self.height)
        frame[max(0, scan_y - 2) : min(self.height, scan_y + 2), :] = 255

        # Invert a dynamic box indicator
        box_x = int((frame_idx * 11) % max(1, self.width - 40))
        box_y = int((frame_idx * 7) % max(1, self.height - 40))
        frame[box_y : box_y + 40, box_x : box_x + 40] = 255 - frame[box_y : box_y + 40, box_x : box_x + 40]

        return frame


class VideoStreamIngestionLoop:
    """Real-time streaming video ingestion loop supporting cameras, RTSP, and synthetic video."""

    def __init__(
        self,
        source: int | str = 0,
        target_fps: float = 30.0,
        frame_width: int = 640,
        frame_height: int = 480,
        frame_queue: FrameQueue | None = None,
        synthetic_fallback: bool = True,
        on_frame: Callable[[np.ndarray, float], None] | None = None,
    ) -> None:
        self.source = source
        self.target_fps = max(1.0, float(target_fps))
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.frame_queue = frame_queue or FrameQueue(maxsize=30, drop_oldest=True)
        self.synthetic_fallback = synthetic_fallback
        self.on_frame = on_frame

        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._process: subprocess.Popen | None = None
        self._synthetic_gen = SyntheticFrameGenerator(width=frame_width, height=frame_height)
        self._frame_count: int = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start the streaming video ingestion loop in a background daemon thread."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="VideoStreamIngestion")
        self._thread.start()
        logger.info(f"VideoStreamIngestionLoop started for source: {self.source} @ {self.target_fps} FPS")

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the ingestion loop gracefully."""
        if not self._running:
            return
        self._running = False
        self._stop_event.set()

        if self._process is not None:
            try:
                self._process.terminate()
            except Exception:
                pass

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        logger.info("VideoStreamIngestionLoop stopped.")

    def _worker_loop(self) -> None:
        """Ingestion thread main loop."""
        use_synthetic = False
        frame_bytes_size = self.frame_width * self.frame_height * 3

        # Attempt to launch ffmpeg if source is camera or RTSP
        if not str(self.source).lower().startswith("synthetic"):
            cmd = self._build_ffmpeg_command()
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=frame_bytes_size * 2,
                )
            except Exception as e:
                logger.warning(f"Failed to start ffmpeg for source {self.source}: {e}")
                if self.synthetic_fallback:
                    use_synthetic = True
                else:
                    self._running = False
                    return

        frame_interval = 1.0 / self.target_fps
        next_frame_time = time.time()

        while self._running and not self._stop_event.is_set():
            now = time.time()
            if now < next_frame_time:
                time.sleep(max(0.001, next_frame_time - now))
            next_frame_time = time.time() + frame_interval

            frame_data: np.ndarray | None = None

            if not use_synthetic and self._process is not None and self._process.stdout is not None:
                try:
                    raw_bytes = self._process.stdout.read(frame_bytes_size)
                    if len(raw_bytes) == frame_bytes_size:
                        frame_data = np.frombuffer(raw_bytes, dtype=np.uint8).reshape(
                            (self.frame_height, self.frame_width, 3)
                        )
                    else:
                        if self.synthetic_fallback:
                            logger.info("FFmpeg stream ended or unavailable; falling back to synthetic generator.")
                            use_synthetic = True
                        else:
                            break
                except Exception as ex:
                    logger.warning(f"Error reading ffmpeg stream: {ex}")
                    if self.synthetic_fallback:
                        use_synthetic = True
                    else:
                        break

            if use_synthetic or str(self.source).lower().startswith("synthetic"):
                frame_data = self._synthetic_gen.generate(self._frame_count)

            if frame_data is not None:
                capture_time = time.time()
                self._frame_count += 1
                self.frame_queue.put(frame_data, timestamp=capture_time)
                if self.on_frame is not None:
                    try:
                        self.on_frame(frame_data, capture_time)
                    except Exception as e:
                        logger.error(f"Error in on_frame callback: {e}")

        if self._process is not None:
            try:
                self._process.kill()
            except Exception:
                pass
            self._process = None

    def _build_ffmpeg_command(self) -> list[str]:
        """Construct ffmpeg CLI pipeline command based on endpoint and platform."""
        src_str = str(self.source)
        cmd = ["ffmpeg", "-loglevel", "quiet"]

        if src_str.startswith("rtsp://") or src_str.startswith("rtsps://"):
            cmd.extend(["-rtsp_transport", "tcp", "-i", src_str])
        elif src_str.startswith("http://") or src_str.startswith("https://"):
            cmd.extend(["-i", src_str])
        elif sys.platform.startswith("win"):
            cmd.extend(["-f", "dshow", "-i", f"video={src_str}"])
        elif sys.platform.startswith("linux"):
            dev = f"/dev/video{src_str}" if src_str.isdigit() else src_str
            cmd.extend(["-f", "v4l2", "-i", dev])
        elif sys.platform.startswith("darwin"):
            cmd.extend(["-f", "avfoundation", "-i", f"{src_str}:none"])
        else:
            cmd.extend(["-i", src_str])

        cmd.extend(["-vf", f"scale={self.frame_width}:{self.frame_height}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
        return cmd
