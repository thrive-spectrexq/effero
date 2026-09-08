"""Tests for CLI argument parsing and entrypoint subcommands."""

from __future__ import annotations

from pathlib import Path

import pytest

from effero.interfaces.cli import build_parser, main


def test_build_parser_options() -> None:
    parser = build_parser()
    assert parser.prog == "effero"

    # Test init command parsing
    args = parser.parse_args(["init", "my_new_agent"])
    assert args.command == "init"
    assert args.name == "my_new_agent"

    # Test chat command parsing
    args = parser.parse_args(["chat", "hello effero"])
    assert args.command == "chat"
    assert args.message == "hello effero"

    # Test serve command defaults
    args = parser.parse_args(["serve"])
    assert args.command == "serve"
    assert args.host == "0.0.0.0"
    assert args.port == 8000


def test_cli_main_no_args_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([])
    assert code == 0
    captured = capsys.readouterr()
    assert "Effero agent runtime" in captured.out or "usage:" in captured.out


def test_cli_skills_command(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["skills"])
    assert code == 0
    captured = capsys.readouterr()
    # At least some built-in skills should be printed
    assert len(captured.out) > 0


def test_cli_init_command(tmp_path: Path) -> None:
    target_dir = tmp_path / "cli_test_agent"
    code = main(["init", str(target_dir)])
    assert code == 0
    assert (target_dir / "effero.yaml").exists()


def test_cli_config_get_and_set(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Create initial project config
    main(["init", str(tmp_path / "proj")])
    proj_cfg = tmp_path / "proj" / "effero.yaml"
    assert proj_cfg.exists()

    # Test setting model.backend to ollama and model name to qwen3:8b
    code = main(["config", "set", "model.backend", "ollama", "--model", "qwen3:8b", "--config", str(proj_cfg)])
    assert code == 0

    capsys.readouterr()

    # Test config get for the updated model.backend
    code = main(["config", "get", "agent.model.backend", "--config", str(proj_cfg)])
    assert code == 0
    captured = capsys.readouterr()
    assert "ollama" in captured.out

    # Test config get for the updated model
    code = main(["config", "get", "agent.model.model", "--config", str(proj_cfg)])
    assert code == 0
    captured = capsys.readouterr()
    assert "qwen3:8b" in captured.out
