"""Base interface for LLM backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMRequest:
    """A request to an LLM backend."""

    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    system: str | None = None


@dataclass
class ToolCall:
    """A tool call returned by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """A response from an LLM backend."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    backend: str = ""


class LLMBackend(ABC):
    """Abstract base class for LLM backends."""

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to the LLM."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this backend is reachable and configured."""
        ...
