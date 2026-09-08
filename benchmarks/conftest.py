"""Shared fixtures for benchmark tests."""

import sys
from pathlib import Path

# Ensure src is importable when running benchmarks directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
