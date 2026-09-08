"""Effero command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

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

    config_p = subparsers.add_parser("config", help="Manage effero configuration")
    config_sub = config_p.add_subparsers(dest="config_action")

    cfg_set = config_sub.add_parser("set", help="Set configuration value (e.g. model.backend ollama --model qwen3:8b)")
    cfg_set.add_argument("key", help="Configuration path key (e.g. model.backend, agent.name)")
    cfg_set.add_argument("value", help="Configuration value to set")
    cfg_set.add_argument("--model", help="Optional model name override")
    cfg_set.add_argument("--config", help="Path to config file")

    cfg_get = config_sub.add_parser("get", help="Get configuration value")
    cfg_get.add_argument("key", nargs="?", help="Key to read, or empty to display full config")
    cfg_get.add_argument("--config", help="Path to config file")

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
    elif args.command == "config":
        handle_config(args)

    return 0


def handle_config(args: argparse.Namespace) -> None:
    """Handle effero config get and config set subcommands."""
    import yaml

    from effero.config import EfferoConfig

    config_path = getattr(args, "config", None)
    config = EfferoConfig.load(config_path)

    if args.config_action == "set":
        key: str = args.key
        value: str = args.value

        # Support dotted keys (e.g. model.backend, agent.name)
        if key in ("model.backend", "agent.model.backend"):
            config.agent.model.backend = value
        elif key in ("model.name", "agent.model.model", "model"):
            config.agent.model.model = value
        elif key in ("agent.name", "name"):
            config.agent.name = value
        elif key == "safety.enabled":
            config.safety.enabled = value.lower() in ("true", "1", "yes")
        elif key == "safety.policy":
            config.safety.policy = value
        elif key == "safety.kernel_host":
            config.safety.kernel_host = value
        elif key == "safety.kernel_port":
            config.safety.kernel_port = int(value)
        elif key == "fleet.enabled":
            config.fleet.enabled = value.lower() in ("true", "1", "yes")
        else:
            # Generic top-level attribute fallback
            if hasattr(config, key):
                setattr(config, key, value)
            else:
                print(f"Unknown config key: {key}")
                return

        if getattr(args, "model", None):
            config.agent.model.model = args.model

        saved_path = config.save(config_path)
        print(f"Updated configuration written to {saved_path}")

    elif args.config_action == "get":
        data = config.model_dump(mode="python", exclude_none=True)
        get_key: str | None = getattr(args, "key", None)
        if not get_key:
            print(yaml.safe_dump(data, sort_keys=False))
            return

        parts = get_key.split(".")
        curr: Any = data
        for p in parts:
            if isinstance(curr, dict) and p in curr:
                curr = curr[p]
            else:
                print(f"Config key '{get_key}' not found.")
                return
        print(curr)


if __name__ == "__main__":
    sys.exit(main())
