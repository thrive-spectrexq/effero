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


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "effero" in captured.out.lower()


def test_cli_init_existing_directory_raises(tmp_path: Path) -> None:
    target_dir = tmp_path / "already_exists"
    target_dir.mkdir()
    with pytest.raises(FileExistsError):
        main(["init", str(target_dir)])


@pytest.mark.asyncio
async def test_cli_run_chat(capsys: pytest.CaptureFixture[str]) -> None:
    from unittest.mock import AsyncMock, patch

    from effero.interfaces.cli import run_chat

    with patch("effero.core.agent.Agent.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "Agent direct reply"
        await run_chat("test direct message")
        captured = capsys.readouterr()
        assert "Agent direct reply" in captured.out


@pytest.mark.asyncio
async def test_cli_run_repl(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from unittest.mock import AsyncMock, patch

    from effero.interfaces.cli import run_repl

    cfg_file = tmp_path / "effero.yaml"
    cfg_file.write_text("agent:\n  name: test-repl\nsafety:\n  enabled: false\n", encoding="utf-8")

    with patch("effero.core.agent.Agent.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "Repl response"
        inputs = iter(["hello", "", "exit"])
        with patch("builtins.input", side_effect=lambda *args: next(inputs)):
            await run_repl(str(cfg_file))
            mock_chat.assert_called_once_with("hello")


def test_cli_serve_command() -> None:
    from unittest.mock import patch

    with patch("uvicorn.run") as mock_uvicorn:
        code = main(["serve", "--host", "127.0.0.1", "--port", "8088"])
        assert code == 0
        mock_uvicorn.assert_called_once()
