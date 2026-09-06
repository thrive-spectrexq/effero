"""Effero command-line entry point.

Real subcommands (`init`, `run`, `config`) will grow here across
milestones -- see ROADMAP in the top-level README. For now this is a
functional stub so `pip install -e .` gives you a working `effero`
command to build on.
"""

from __future__ import annotations

import argparse
import sys

from effero import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="effero", description="Effero agent runtime")
    parser.add_argument("--version", action="version", version=f"effero {__version__}")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("init", help="Scaffold a new Effero project (not yet implemented)")
    subparsers.add_parser("run", help="Run the Effero runtime (not yet implemented)")
    subparsers.add_parser("config", help="Get/set runtime configuration (not yet implemented)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    print(f"'{args.command}' is not implemented yet -- see ROADMAP in the top-level README.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
