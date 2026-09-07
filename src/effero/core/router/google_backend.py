"""Google Gemini backend implementation."""

from __future__ import annotations

import os
from typing import Any

from effero.core.router.base import LLMBackend, LLMRequest, LLMResponse, ToolCall


class GoogleBackend(LLMBackend):
    """Google Gemini backend implementation."""

    def __init__(self, model: str = "gemini-2.5-flash", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to the LLM."""
        try:
            import google.genai as genai
            from google.genai import types
        except ImportError:
            raise RuntimeError("google-genai package is not installed. Install it with `pip install google-genai`.")

        if not self.api_key:
            raise RuntimeError("Gemini API key is not set.")

        client = genai.Client(api_key=self.api_key)

        # Convert messages to Gemini Content format
        contents = []
        for msg in request.messages:
            role = msg.get("role", "user")
            # Gemini uses "user" and "model"
            if role == "assistant":
                role = "model"

            # Simple conversion, ignoring complex parts for now
            content_str = msg.get("content", "")
            contents.append(types.Content(role=role, parts=[types.Part.from_text(content_str)]))

        config_kwargs: dict[str, Any] = {
            "temperature": request.temperature,
            "max_output_tokens": request.max_tokens,
        }

        if request.system:
            config_kwargs["system_instruction"] = request.system

        if request.tools:
            tools = []
            for tool in request.tools:
                # Basic mapping to Gemini's FunctionDeclaration
                props = {}
                required = []
                if "parameters" in tool and "properties" in tool["parameters"]:
                    for k, v in tool["parameters"]["properties"].items():
                        # Simple type mapping
                        t_type = types.Type.STRING
                        if v.get("type") == "integer":
                            t_type = types.Type.INTEGER
                        elif v.get("type") == "number":
                            t_type = types.Type.NUMBER
                        elif v.get("type") == "boolean":
                            t_type = types.Type.BOOLEAN
                        elif v.get("type") == "array":
                            t_type = types.Type.ARRAY
                        elif v.get("type") == "object":
                            t_type = types.Type.OBJECT

                        schema = types.Schema(type=t_type, description=v.get("description", ""))
                        props[k] = schema

                    required = tool["parameters"].get("required", [])

                func_decl = types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=types.Schema(type=types.Type.OBJECT, properties=props, required=required)
                    if props
                    else None,
                )
                tools.append(types.Tool(function_declarations=[func_decl]))

            config_kwargs["tools"] = tools

        config = types.GenerateContentConfig(**config_kwargs)

        try:
            # We use the synchronous generate_content wrapped in asyncio or assume the SDK handles it
            # The google-genai SDK has client.aio.models.generate_content
            if hasattr(client, "aio"):
                response = await client.aio.models.generate_content(model=self.model, contents=contents, config=config)
            else:
                import asyncio

                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=self.model,
                    contents=contents,
                    config=config,
                )
        except Exception as e:
            raise RuntimeError(f"Google Gemini API error: {e}") from e

        content = None
        tool_calls = []

        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.text:
                    if content is None:
                        content = part.text
                    else:
                        content += "\n" + part.text
                elif part.function_call:
                    fc = part.function_call
                    # Extract args
                    args = {}
                    if fc.args:
                        # Depending on SDK version, args might be a dict or a Struct
                        if isinstance(fc.args, dict):
                            args = fc.args
                        elif hasattr(fc.args, "items"):  # Might be proto map
                            args = {k: v for k, v in fc.args.items()}
                        else:
                            # fallback to try casting
                            try:
                                args = dict(fc.args)
                            except Exception:
                                pass

                    tool_calls.append(
                        ToolCall(
                            id=f"call_{fc.name}",  # Gemini doesn't always provide an ID, fake one
                            name=fc.name,
                            arguments=args,
                        )
                    )

        usage = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = {
                "prompt_token_count": getattr(response.usage_metadata, "prompt_token_count", 0),
                "candidates_token_count": getattr(response.usage_metadata, "candidates_token_count", 0),
                "total_token_count": getattr(response.usage_metadata, "total_token_count", 0),
            }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            model=self.model,
            backend="google",
        )

    async def is_available(self) -> bool:
        """Check if this backend is reachable and configured."""
        try:
            import google.genai

            return bool(self.api_key)
        except ImportError:
            return False
