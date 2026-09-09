"""Anthropic backend implementation."""

from __future__ import annotations

import os
from typing import Any

from effero.core.router.base import LLMBackend, LLMRequest, LLMResponse, ToolCall


class AnthropicBackend(LLMBackend):
    """Anthropic backend implementation."""

    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to the LLM."""
        try:
            import anthropic
            from anthropic import AsyncAnthropic
        except ImportError as e:
            raise RuntimeError("anthropic package is not installed. Install it with `pip install anthropic`.") from e

        if not self.api_key:
            raise RuntimeError("Anthropic API key is not set.")

        client = AsyncAnthropic(api_key=self.api_key)

        # Anthropic has a separate system parameter
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": request.messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        if request.system:
            kwargs["system"] = request.system

        if request.tools:
            anthropic_tools = []
            for tool in request.tools:
                anthropic_tool = {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("parameters", {"type": "object", "properties": {}}),
                }
                anthropic_tools.append(anthropic_tool)
            kwargs["tools"] = anthropic_tools

        try:
            response = await client.messages.create(**kwargs)
        except Exception as e:
            raise RuntimeError(f"Anthropic API error: {e}") from e

        content = None
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                if content is None:
                    content = block.text
                else:
                    content += "\n" + block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    )
                )

        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "input_tokens": getattr(response.usage, "input_tokens", 0),
                "output_tokens": getattr(response.usage, "output_tokens", 0),
            }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            model=response.model,
            backend="anthropic",
        )

    async def is_available(self) -> bool:
        """Check if this backend is reachable and configured."""
        try:
            import anthropic

            return bool(self.api_key)
        except ImportError:
            return False
