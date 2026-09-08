"""Episodic memory module for Effero."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class EpisodicMemory:
    def __init__(self, session_dir: Path | str | None = None):
        if session_dir is None:
            session_dir = Path.cwd() / "sessions"
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        session_id = str(int(time.time()))
        self.session_path = self.session_dir / f"session_{session_id}.jsonl"

    def get_session_path(self) -> Path:
        return self.session_path

    def record(self, event_type: str, data: dict[str, Any]) -> None:
        entry = {
            "timestamp": time.time(),
            "type": event_type,
            "data": data,
        }
        try:
            with open(self.session_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write episodic memory: {e}")

    def load_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Load the most recent episodic events from disk without reading the full file into RAM."""
        if not self.session_path.exists() or limit <= 0:
            return []

        entries: list[dict[str, Any]] = []
        chunk_size = 8192

        try:
            with open(self.session_path, "rb") as f:
                f.seek(0, 2)
                file_size = f.tell()
                pos = file_size
                buffer = b""

                while pos > 0 and len(entries) < limit:
                    read_size = min(chunk_size, pos)
                    pos -= read_size
                    f.seek(pos)
                    chunk = f.read(read_size)
                    buffer = chunk + buffer

                    lines = buffer.split(b"\n")
                    buffer = lines[0]

                    for raw_line in reversed(lines[1:]):
                        line_str = raw_line.decode("utf-8", errors="replace").strip()
                        if line_str and len(entries) < limit:
                            try:
                                entries.append(json.loads(line_str))
                            except json.JSONDecodeError:
                                continue

                if pos == 0 and buffer.strip() and len(entries) < limit:
                    line_str = buffer.decode("utf-8", errors="replace").strip()
                    if line_str:
                        try:
                            entries.append(json.loads(line_str))
                        except json.JSONDecodeError:
                            pass

            entries.reverse()
        except Exception as e:
            logger.error(f"Failed to read episodic memory: {e}")

        return entries
