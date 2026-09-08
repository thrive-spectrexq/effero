"""Model Router layer for Effero."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from effero.core.router.base import LLMBackend, LLMRequest, LLMResponse, ToolCall
    from effero.core.router.router import ModelRouter

__all__ = [
    "LLMBackend",
    "LLMRequest",
    "LLMResponse",
    "ModelRouter",
    "ToolCall",
]


def __getattr__(name: str) -> Any:
    if name in ("LLMBackend", "LLMRequest", "LLMResponse", "ToolCall"):
        import effero.core.router.base as base_mod

        return getattr(base_mod, name)
    elif name == "ModelRouter":
        import effero.core.router.router as router_mod

        return getattr(router_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
