"""Effero command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from effero import __version__


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


async def run_repl(config_path: str | None = None) -> None:
    from effero.config import EfferoConfig
    from effero.core.agent import Agent

    if config_path:
        config = EfferoConfig.load(config_path)
    else:
        config = EfferoConfig.load()

    agent = Agent(config=config)
    await agent.start()

    print(f"Effero {__version__} REPL. Type 'exit' to quit.")
    loop = asyncio.get_running_loop()
    try:
        while True:
            try:
                user_input = await loop.run_in_executor(None, lambda: input(">> "))
            except EOFError:
                break

            if user_input.strip() in ("exit", "quit"):
                break
            if not user_input.strip():
                continue

            response = await agent.chat(user_input)
            print(f"\n{response}\n")
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        await agent.stop()


async def run_chat(message: str) -> None:
    from effero.core.agent import Agent

    agent = Agent()
    await agent.start()
    try:
        response = await agent.chat(message)
        print(response)
    finally:
        await agent.stop()


def init_project(name: str) -> None:
    path = Path(name)
    if path.exists():
        print(f"Directory {name} already exists.")
        raise FileExistsError(f"Directory {name} already exists.")

    path.mkdir(parents=True)
    project_name = path.name
    yaml_content = f"""agent:
  name: "{project_name}"
  model:
    backend: openai
    model: gpt-4o
safety:
  enabled: false
  kernel_host: "127.0.0.1"
  kernel_port: 9400
"""
    (path / "effero.yaml").write_text(yaml_content)
    print(f"Initialized Effero project in {name}/")
    print(f"cd {name} and run `effero run`")


def list_skills() -> None:
    # Need to load skills first
    import importlib

    from effero.sdk import BUILTIN_SKILL_MODULES
    from effero.sdk.skill import registry

    for mod_name in BUILTIN_SKILL_MODULES:
        try:
            importlib.import_module(mod_name)
        except ImportError:
            pass

    for name in registry.list():
        spec = registry.get(name)
        print(f"- {name} [{spec.safety_class}]")
        print(f"  {spec.description}")
        print()


async def serve_mcp() -> None:
    import importlib

    from effero.protocols.mcp_server import MCPServer
    from effero.sdk import BUILTIN_SKILL_MODULES
    from effero.sdk.skill import registry

    for mod_name in BUILTIN_SKILL_MODULES:
        try:
            importlib.import_module(mod_name)
        except ImportError:
            pass

    server = MCPServer(registry)
    loop = asyncio.get_running_loop()

    try:
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            try:
                request = json.loads(line)
                response = await server.handle_request(request)
                if response:
                    print(json.dumps(response), flush=True)
            except json.JSONDecodeError:
                pass
    except KeyboardInterrupt:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="effero", description="Effero agent runtime")
    parser.add_argument("--version", action="version", version=f"effero {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    run_p = subparsers.add_parser("run", help="Start interactive REPL loop")
    run_p.add_argument("--config", help="Path to config file")

    chat_p = subparsers.add_parser("chat", help="Send a single message")
    chat_p.add_argument("message", help="Message to send")

    init_p = subparsers.add_parser("init", help="Scaffold a new Effero project")
    init_p.add_argument("name", help="Project name")

    subparsers.add_parser("skills", help="List registered skills")
    subparsers.add_parser("mcp-serve", help="Start as MCP server on stdio")

    serve_p = subparsers.add_parser("serve", help="Start HTTP & WebSocket API server")
    serve_p.add_argument("--host", default="0.0.0.0", help="Host to bind server (default: 0.0.0.0)")
    serve_p.add_argument("--port", type=int, default=8000, help="Port to bind server (default: 8000)")

    return parser


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "run":
        asyncio.run(run_repl(args.config))
    elif args.command == "chat":
        asyncio.run(run_chat(args.message))
    elif args.command == "init":
        init_project(args.name)
    elif args.command == "skills":
        list_skills()
    elif args.command == "mcp-serve":
        asyncio.run(serve_mcp())
    elif args.command == "serve":
        import uvicorn

        from effero.interfaces.server import create_app

        app = create_app()
        uvicorn.run(app, host=args.host, port=args.port)

    return 0


if __name__ == "__main__":
    sys.exit(main())
