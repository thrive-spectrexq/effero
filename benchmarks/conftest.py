"""Shared fixtures for benchmark tests."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

# Ensure src is importable when running benchmarks directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def benchmark() -> Callable[..., Any]:
    """Fallback runner if pytest-benchmark plugin is not installed."""

    def _runner(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    return _runner
