"""Tests for examples/runner.py reusable agent runner."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from examples.runner import main, run_agent_loop  # noqa: E402


@pytest.mark.asyncio
async def test_run_agent_loop_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        await run_agent_loop(tmp_path / "nonexistent.yaml")


@pytest.mark.asyncio
async def test_run_agent_loop_interactive(tmp_path: Path):
    cfg_path = tmp_path / "effero.yaml"
    cfg_path.write_text(
        """
agent:
  name: test-runner-agent
  model:
    backend: ollama
    model: qwen3:8b
safety:
  enabled: false
""",
        encoding="utf-8",
    )

    with patch("effero.core.agent.Agent.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "Mocked chat response"
        # Simulate user inputs: "hello", then "quit"
        inputs = iter(["hello", "quit"])

        with patch("builtins.input", side_effect=lambda *args: next(inputs)):
            await run_agent_loop(cfg_path)
            mock_chat.assert_called_once_with("hello")


def test_examples_runner_cli_main(tmp_path: Path):
    cfg_path = tmp_path / "effero.yaml"
    cfg_path.write_text("agent:\n  name: test\nsafety:\n  enabled: false\n", encoding="utf-8")

    with patch("sys.argv", ["runner.py", str(cfg_path)]):
        with patch("examples.runner.run_agent_loop", new_callable=AsyncMock) as mock_run:
            main()
            mock_run.assert_called_once_with(str(cfg_path))
