"""Tests for scripts/lint_skills.py skill registry and config validation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_lint_skills_passes():
    """Verify that lint_skills.py executes with exit code 0 against the repository."""
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/lint_skills.py"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"lint_skills failed with stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "All skills passed validation" in result.stdout
