"""OpenAI backend implementation."""

from __future__ import annotations

import json
import os
from typing import Any

from effero.core.router.base import LLMBackend, LLMRequest, LLMResponse, ToolCall


class OpenAIBackend(LLMBackend):
    """OpenAI backend implementation."""

    def __init__(self, model: str, api_key: str | None = None, base_url: str | None = None):
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to the LLM."""
        try:
            import openai
            from openai import AsyncOpenAI
        except ImportError:
            raise RuntimeError("openai package is not installed. Install it with `pip install openai`.")

        if not self.api_key:
            raise RuntimeError("OpenAI API key is not set.")

        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if request.tools:
            kwargs["tools"] = [{"type": "function", "function": tool} for tool in request.tools]

        try:
            response = await client.chat.completions.create(**kwargs)
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}") from e

        choice = response.choices[0]

        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                if tc.type == "function":
                    args = {}
                    if tc.function.arguments:
                        try:
                            args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            args = {"_raw_args": tc.function.arguments}
                    tool_calls.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=args,
                        )
                    )

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
            usage=usage,
            model=response.model,
            backend="openai",
        )

    async def is_available(self) -> bool:
        """Check if this backend is reachable and configured."""
        try:
            import openai

            return bool(self.api_key)
        except ImportError:
            return False
