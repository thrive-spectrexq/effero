"""Tests for CLI."""

from __future__ import annotations

import tempfile
from pathlib import Path

from effero.interfaces.cli import init_project


def test_init_creates_project() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = Path(tmpdir) / "test-project"
        init_project(str(project_path))
        assert project_path.exists()
        config_file = project_path / "effero.yaml"
        assert config_file.exists()
        content = config_file.read_text()
        assert "test-project" in content
        assert "agent:" in content
