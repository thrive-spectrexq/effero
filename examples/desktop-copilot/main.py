"""Desktop copilot demo — shows Effero controlling local computer resources."""
from __future__ import annotations

import asyncio

from effero.config import EfferoConfig
from effero.core.agent import Agent


async def main() -> None:
    config = EfferoConfig.load("effero.yaml")
    agent = Agent(config)
    await agent.start()
    
    print(f"Agent '{config.agent.name}' ready with skills: {agent.available_skills()}")
    print("Type 'quit' to exit.\n")
    
    while True:
        try:
            user_input = input("> ")
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.strip().lower() in ("quit", "exit"):
            break
        response = await agent.chat(user_input)
        print(f"\n{response}\n")
    
    await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
