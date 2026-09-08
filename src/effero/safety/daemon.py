"""Safety daemon manager — automatically manages effero-safety-kerneld lifecycle."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class SafetyDaemonManager:
    """Discovers, starts, monitors, and stops the Rust safety kernel daemon."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9400,
        policy_path: str | Path | None = None,
        custom_binary_path: str | Path | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.policy_path = Path(policy_path) if policy_path else None
        self.custom_binary_path = Path(custom_binary_path) if custom_binary_path else None
        self._process: asyncio.subprocess.Process | None = None
        self._owns_process = False

    def find_binary(self) -> Path | None:
        """Find the effero-safety-kerneld binary on PATH or local workspace targets."""
        if self.custom_binary_path and self.custom_binary_path.exists():
            return self.custom_binary_path

        # Check system PATH
        which_path = shutil.which("effero-safety-kerneld")
        if which_path:
            return Path(which_path)

        # Check workspace target directories (target/release, target/debug)
        # Assuming repo root relative to this module
        current = Path(__file__).resolve().parents[3]  # repo root
        candidates = [
            current / "target" / "release" / "effero-safety-kerneld.exe",
            current / "target" / "release" / "effero-safety-kerneld",
            current / "target" / "debug" / "effero-safety-kerneld.exe",
            current / "target" / "debug" / "effero-safety-kerneld",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

        return None

    async def is_running(self) -> bool:
        """Check if a safety kernel daemon is already accepting connections on host:port."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=0.5,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (TimeoutError, OSError):
            return False

    async def ensure_running(self) -> bool:
        """Ensure the safety daemon is running; spawn it if absent and binary is found."""
        if await self.is_running():
            logger.info(f"Safety kernel already running on {self.host}:{self.port}")
            return True

        binary = self.find_binary()
        if not binary:
            logger.warning("effero-safety-kerneld binary not found. Skipping auto-spawn.")
            return False

        args = [str(binary), "--port", str(self.port), "--host", self.host]
        if self.policy_path and self.policy_path.exists():
            args.extend(["--policy", str(self.policy_path)])

        logger.info(f"Auto-spawning safety kernel daemon: {' '.join(args)}")
        try:
            self._process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._owns_process = True

            # Wait for daemon to bind and respond to TCP connections
            for _ in range(20):
                await asyncio.sleep(0.1)
                if await self.is_running():
                    logger.info(f"Safety kernel daemon ready on {self.host}:{self.port}")
                    return True

            logger.error("Safety kernel daemon started but did not respond on port in time")
            await self.stop()
            return False
        except Exception as e:
            logger.error(f"Failed to spawn safety kernel daemon: {e}")
            return False

    async def stop(self) -> None:
        """Stop the child safety daemon process if we started it."""
        if self._owns_process and self._process:
            logger.info("Stopping safety kernel daemon...")
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except (ProcessLookupError, OSError):
                pass
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
            self._owns_process = False
            logger.info("Safety kernel daemon stopped")
