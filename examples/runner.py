"""Reusable runner for interactive Effero agent examples."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from effero.config import EfferoConfig
from effero.core.agent import Agent


async def run_agent_loop(config_path: str | Path = "effero.yaml") -> None:
    """Run an interactive console REPL for an Effero agent defined by effero.yaml."""
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {cfg_file}")

    config = EfferoConfig.load(str(cfg_file))
    agent = Agent(config)
    await agent.start()

    print(f"Agent '{config.agent.name}' ready with skills: {agent.available_skills()}")
    print("Type 'quit' or 'exit' to end session.\n")

    loop = asyncio.get_running_loop()
    try:
        while True:
            try:
                user_input = await loop.run_in_executor(None, lambda: input("> "))
            except (EOFError, KeyboardInterrupt):
                break
            if user_input.strip().lower() in ("quit", "exit"):
                break
            if not user_input.strip():
                continue
            response = await agent.chat(user_input)
            print(f"\n{response}\n")
    finally:
        await agent.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an Effero example agent")
    parser.add_argument(
        "config",
        nargs="?",
        default="effero.yaml",
        help="Path to effero.yaml configuration file (default: effero.yaml)",
    )
    args = parser.parse_args()
    try:
        asyncio.run(run_agent_loop(args.config))
    except KeyboardInterrupt:
        print("\nSession terminated.")
        sys.exit(0)


if __name__ == "__main__":
    main()
