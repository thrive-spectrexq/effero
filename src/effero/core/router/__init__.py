"""Model Router layer for Effero."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from effero.core.router.base import LLMBackend, LLMRequest, LLMResponse, ToolCall
    from effero.core.router.router import ModelRouter
    from effero.core.router.scripted_backend import ScriptedBackend

__all__ = [
    "LLMBackend",
    "LLMRequest",
    "LLMResponse",
    "ModelRouter",
    "ScriptedBackend",
    "ToolCall",
]


def __getattr__(name: str) -> Any:
    if name in ("LLMBackend", "LLMRequest", "LLMResponse", "ToolCall"):
        import effero.core.router.base as base_mod

        return getattr(base_mod, name)
    elif name == "ModelRouter":
        import effero.core.router.router as router_mod

        return getattr(router_mod, name)
    elif name == "ScriptedBackend":
        import effero.core.router.scripted_backend as scripted_mod

        return getattr(scripted_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
