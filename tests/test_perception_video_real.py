"""Tests for real-time video stream ingestion loop and bounded frame queue."""

from __future__ import annotations

import asyncio
import time

import numpy as np
import pytest

from effero.perception.vision.stream import (
    FrameQueue,
    SyntheticFrameGenerator,
    VideoStreamIngestionLoop,
)


def test_frame_queue_init() -> None:
    queue = FrameQueue(maxsize=10, drop_oldest=True)
    assert queue.maxsize == 10
    assert queue.drop_oldest is True
    assert queue.queue_depth == 0
    assert queue.frames_ingested == 0
    assert queue.frames_dropped == 0
    assert queue.drop_rate == 0.0

    with pytest.raises(ValueError, match="maxsize must be positive"):
        FrameQueue(maxsize=0)


def test_frame_queue_fifo_order() -> None:
    queue = FrameQueue(maxsize=5, drop_oldest=True)

    f1 = np.ones((10, 10, 3), dtype=np.uint8) * 1
    f2 = np.ones((10, 10, 3), dtype=np.uint8) * 2

    assert queue.put(f1, timestamp=100.0) is True
    assert queue.put(f2, timestamp=101.0) is True
    assert queue.queue_depth == 2
    assert queue.frames_ingested == 2

    # Oldest first
    res1 = queue.get(timeout=0.1)
    assert res1 is not None
    assert np.array_equal(res1[0], f1)
    assert res1[1] == 100.0

    res2 = queue.get_nowait()
    assert res2 is not None
    assert np.array_equal(res2[0], f2)
    assert res2[1] == 101.0

    assert queue.queue_depth == 0
    assert queue.get_nowait() is None


def test_frame_queue_drop_oldest_policy() -> None:
    queue = FrameQueue(maxsize=3, drop_oldest=True)

    for i in range(1, 6):  # Ingest 5 frames: 1, 2, 3, 4, 5
        frame = np.ones((10, 10, 3), dtype=np.uint8) * i
        queue.put(frame, timestamp=float(i))

    stats = queue.get_stats()
    assert stats["frames_ingested"] == 5
    assert stats["frames_dropped"] == 2
    assert stats["queue_depth"] == 3
    assert stats["drop_rate"] == 2 / 5

    # Retained frames in FIFO should be 3, 4, 5
    res1 = queue.get()
    assert res1 is not None and res1[0][0, 0, 0] == 3
    res2 = queue.get()
    assert res2 is not None and res2[0][0, 0, 0] == 4
    res3 = queue.get()
    assert res3 is not None and res3[0][0, 0, 0] == 5
    assert queue.queue_depth == 0


def test_frame_queue_drop_newest_policy() -> None:
    queue = FrameQueue(maxsize=2, drop_oldest=False)

    f1 = np.ones((5, 5, 3), dtype=np.uint8) * 10
    f2 = np.ones((5, 5, 3), dtype=np.uint8) * 20
    f3 = np.ones((5, 5, 3), dtype=np.uint8) * 30

    assert queue.put(f1) is True
    assert queue.put(f2) is True
    # Overflow with drop_oldest=False
    assert queue.put(f3) is False

    assert queue.frames_dropped == 1
    assert queue.queue_depth == 2

    res1 = queue.get()
    assert res1 is not None and res1[0][0, 0, 0] == 10
    res2 = queue.get()
    assert res2 is not None and res2[0][0, 0, 0] == 20


def test_frame_queue_latest_peek_and_clear() -> None:
    queue = FrameQueue(maxsize=4)
    assert queue.get_latest() is None
    assert queue.get_latest_frame() is None

    f1 = np.zeros((4, 4, 3), dtype=np.uint8)
    f2 = np.ones((4, 4, 3), dtype=np.uint8) * 99
    queue.put(f1, timestamp=1.0)
    queue.put(f2, timestamp=2.0)

    latest = queue.get_latest()
    assert latest is not None
    assert np.array_equal(latest, f2)

    latest_frame = queue.get_latest_frame()
    assert latest_frame is not None
    assert np.array_equal(latest_frame[0], f2)
    assert latest_frame[1] == 2.0

    # Peeking does not remove frames
    assert queue.queue_depth == 2

    queue.clear()
    assert queue.queue_depth == 0
    assert queue.get_latest() is None


@pytest.mark.asyncio
async def test_frame_queue_async_read_frame() -> None:
    queue = FrameQueue(maxsize=5)

    # Empty read with brief timeout
    res = await queue.read_frame(timeout=0.05)
    assert res is None

    # Async read with incoming frame
    frame = np.ones((8, 8, 3), dtype=np.uint8) * 42

    async def _producer():
        await asyncio.sleep(0.05)
        queue.put(frame)

    producer_task = asyncio.create_task(_producer())
    consumed = await queue.read_frame(timeout=1.0)
    await producer_task

    assert consumed is not None
    assert np.array_equal(consumed, frame)


def test_synthetic_frame_generator() -> None:
    gen = SyntheticFrameGenerator(width=160, height=120)
    f0 = gen.generate(0)
    f1 = gen.generate(1)

    assert f0.shape == (120, 160, 3)
    assert f0.dtype == np.uint8
    assert not np.array_equal(f0, f1), "Consecutive synthetic frames must have dynamic temporal variation"


def test_video_stream_ingestion_lifecycle_and_callback() -> None:
    callback_frames: list[tuple[np.ndarray, float]] = []

    def on_frame(frame: np.ndarray, ts: float) -> None:
        callback_frames.append((frame, ts))

    loop = VideoStreamIngestionLoop(
        source="synthetic",
        target_fps=20.0,
        frame_width=80,
        frame_height=60,
        on_frame=on_frame,
    )

    assert loop.is_running is False
    loop.start()
    assert loop.is_running is True

    # Allow ~250ms for frames to ingest (expected ~4-6 frames at 20 FPS)
    time.sleep(0.25)
    loop.stop()
    assert loop.is_running is False

    stats = loop.frame_queue.get_stats()
    assert stats["frames_ingested"] >= 2, f"Expected at least 2 frames, got {stats}"
    assert stats["queue_depth"] >= 2
    assert len(callback_frames) == stats["frames_ingested"]

    frame_data, frame_ts = loop.frame_queue.get_latest_frame()
    assert frame_data.shape == (60, 80, 3)
    assert frame_ts > 0.0


def test_video_stream_ffmpeg_command_builder() -> None:
    loop_rtsp = VideoStreamIngestionLoop(source="rtsp://192.168.1.50:554/live", target_fps=30.0)
    cmd_rtsp = loop_rtsp._build_ffmpeg_command()
    assert "ffmpeg" in cmd_rtsp[0]
    assert "-rtsp_transport" in cmd_rtsp
    assert "tcp" in cmd_rtsp
    assert "rtsp://192.168.1.50:554/live" in cmd_rtsp
    assert "rawvideo" in cmd_rtsp
    assert "rgb24" in cmd_rtsp

    loop_cam = VideoStreamIngestionLoop(source="0", frame_width=320, frame_height=240)
    cmd_cam = loop_cam._build_ffmpeg_command()
    assert "scale=320:240" in " ".join(cmd_cam)


@pytest.mark.asyncio
async def test_color_blob_detector_and_vision_pipeline() -> None:
    import io

    from PIL import Image

    from effero.core.event_bus import EventBus
    from effero.perception.vision.detector import ColorBlobDetector
    from effero.perception.vision.pipeline import VisionPipeline

    # Create image with red blob
    img = Image.new("RGB", (100, 100), color=(0, 0, 0))
    # Draw red square in center
    for y in range(40, 60):
        for x in range(40, 60):
            img.putpixel((x, y), (255, 0, 0))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    detector = ColorBlobDetector(target_color="red", threshold=100)
    detections = await detector.detect(img_bytes)
    assert len(detections) >= 1
    assert "red" in detections[0].label
    assert detections[0].confidence >= 0.5
    min_x, min_y, max_x, max_y = detections[0].bbox
    assert min_x <= 40 and max_x >= 59
    assert min_y <= 40 and max_y >= 59

    # Test VisionPipeline event publication
    bus = EventBus()
    pipeline = VisionPipeline(event_bus=bus, detector_backend=detector)
    await pipeline.start()
    assert pipeline.running is True

    detected = await pipeline.process_frame(img_bytes)
    assert len(detected) >= 1

    # Check published event in history
    history = bus.get_history(topic_pattern="perception.vision.detection")
    assert len(history) == 1
    event = history[0]
    assert isinstance(event.timestamp, float)
    assert "detections" in event.data

    await pipeline.stop()
    assert pipeline.running is False

    # Test from_config
    pipe_cfg = VisionPipeline.from_config({"detector": {"type": "blob", "target_color": "bright"}}, bus)
    assert isinstance(pipe_cfg.detector_backend, ColorBlobDetector)


@pytest.mark.asyncio
async def test_audio_pipeline_and_backends() -> None:
    from effero.core.event_bus import EventBus
    from effero.perception.audio.asr import EnergyVADASR
    from effero.perception.audio.pipeline import AudioPipeline
    from effero.perception.audio.tts import ToneSynthesizerTTS

    tts = ToneSynthesizerTTS(sample_rate=16000, base_freq=440.0)
    audio_wav = await tts.synthesize("Turn right and grasp the tool")
    assert len(audio_wav) > 44  # WAV header is 44 bytes
    assert audio_wav[:4] == b"RIFF"
    assert audio_wav[8:12] == b"WAVE"

    asr = EnergyVADASR(energy_threshold=0.005)
    transcription = await asr.transcribe(audio_wav)
    assert transcription.confidence is not None
    assert transcription.confidence > 0.5
    assert "[speech_detected" in transcription.text or len(transcription.text) > 0

    bus = EventBus()
    pipeline = AudioPipeline(event_bus=bus, asr_backend=asr, tts_backend=tts)
    await pipeline.start()
    assert pipeline.running is True

    text_res = await pipeline.process_audio(audio_wav)
    assert len(text_res) > 0

    spoken_bytes = await pipeline.speak("Confirmation received")
    assert spoken_bytes[:4] == b"RIFF"

    # Check published events with float timestamps
    utterance_events = bus.get_history("perception.audio.utterance")
    assert len(utterance_events) == 1
    assert isinstance(utterance_events[0].timestamp, float)

    speech_events = bus.get_history("perception.audio.speech")
    assert len(speech_events) == 1
    assert isinstance(speech_events[0].timestamp, float)

    await pipeline.stop()
    assert pipeline.running is False

    # Test from_config
    pipe_cfg = AudioPipeline.from_config({"asr": {"type": "vad"}, "tts": {"type": "tone"}}, bus)
    assert isinstance(pipe_cfg.asr_backend, EnergyVADASR)
    assert isinstance(pipe_cfg.tts_backend, ToneSynthesizerTTS)


@pytest.mark.asyncio
async def test_sensor_pipeline_and_system_metrics() -> None:
    from effero.core.event_bus import EventBus
    from effero.perception.sensors.pipeline import SensorPipeline, SystemMetricsSensor

    sensor = SystemMetricsSensor()
    readings = await sensor.read()
    assert len(readings) == 3

    ids = [r.sensor_id for r in readings]
    assert "system.cpu.percent" in ids
    assert "system.memory.percent" in ids
    assert "system.disk.percent" in ids

    for r in readings:
        assert isinstance(r.timestamp, float)
        assert isinstance(r.value, (int, float))
        assert r.unit == "%"

    bus = EventBus()
    pipeline = SensorPipeline(event_bus=bus, sensor_backend=sensor, poll_interval=0.05)
    await pipeline.start()
    assert pipeline.running is True

    # Allow poll loop to trigger
    await asyncio.sleep(0.12)
    await pipeline.stop()
    assert pipeline.running is False

    events = bus.get_history("perception.sensor.reading")
    assert len(events) >= 1
    for ev in events:
        assert isinstance(ev.timestamp, float)
        assert "sensor_id" in ev.data
        assert "value" in ev.data

    # Test from_config
    pipe_cfg = SensorPipeline.from_config({"poll_interval": 0.5}, bus)
    assert isinstance(pipe_cfg.sensor_backend, SystemMetricsSensor)
