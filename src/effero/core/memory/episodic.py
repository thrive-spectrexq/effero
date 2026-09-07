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
        if not self.session_path.exists():
            return []

        entries = []
        try:
            with open(self.session_path) as f:
                lines = f.readlines()
                for line in lines[-limit:]:
                    if line.strip():
                        entries.append(json.loads(line))
        except Exception as e:
            logger.error(f"Failed to read episodic memory: {e}")

        return entries
