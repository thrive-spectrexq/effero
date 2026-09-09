"""Desktop copilot demo — shows Effero controlling local computer resources."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure repository root is on path when executed directly
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.runner import run_agent_loop  # noqa: E402

if __name__ == "__main__":
    asyncio.run(run_agent_loop(Path(__file__).parent / "effero.yaml"))
