"""Effero: one runtime for perceiving, reasoning, and acting across
computers, robots, and connected devices.

See the top-level README.md for the full architecture and philosophy.
"""

__version__ = "0.1.10"


from typing import Any


# Lazy load to avoid cyclic imports or missing dependencies
def __getattr__(name: str) -> Any:
    if name == "Agent":
        from effero.core.agent import Agent

        return Agent
    if name == "EfferoConfig":
        from effero.config import EfferoConfig

        return EfferoConfig
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["Agent", "EfferoConfig"]
