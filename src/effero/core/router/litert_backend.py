"""Google AI Edge LiteRT-LM backend implementation."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from effero.core.router.base import LLMBackend, LLMRequest, LLMResponse, ToolCall

logger = logging.getLogger(__name__)


class LiteRTLMBackend(LLMBackend):
    """LiteRT-LM on-device backend utilizing Google AI Edge runtime.

    Supports running .litertlm model files with native CPU, GPU, and NPU acceleration.
    """

    def __init__(self, model: str, device: str = "auto") -> None:
        self.model = model
        self.device = device.lower()
        self._engine: Any = None
        self._lock = asyncio.Lock()

    def _resolve_backend_type(self, litert_lm: Any) -> Any:
        """Resolve device target to litert_lm Backend enum/factory."""
        if not hasattr(litert_lm, "Backend"):
            return None

        if self.device == "gpu" and hasattr(litert_lm.Backend, "GPU"):
            return litert_lm.Backend.GPU()
        elif self.device == "npu" and hasattr(litert_lm.Backend, "NPU"):
            return litert_lm.Backend.NPU()
        elif self.device == "cpu" and hasattr(litert_lm.Backend, "CPU"):
            return litert_lm.Backend.CPU()

        # Auto resolution: try GPU or NPU if available, otherwise CPU
        if hasattr(litert_lm.Backend, "GPU"):
            try:
                return litert_lm.Backend.GPU()
            except Exception:
                pass
        if hasattr(litert_lm.Backend, "CPU"):
            return litert_lm.Backend.CPU()
        return None

    def _init_engine(self) -> Any:
        """Initialize and cache the LiteRT-LM Engine instance."""
        if self._engine is not None:
            return self._engine

        try:
            import litert_lm
        except ImportError as e:
            raise RuntimeError(
                "litert-lm-api package is not installed. Install it with `pip install effero[litert]` "
                "or `pip install litert-lm-api`."
            ) from e

        backend_target = self._resolve_backend_type(litert_lm)
        kwargs: dict[str, Any] = {}
        if backend_target is not None:
            kwargs["backend"] = backend_target

        logger.info(f"Initializing LiteRT-LM Engine with model='{self.model}', device='{self.device}'")
        self._engine = litert_lm.Engine(self.model, **kwargs)
        return self._engine

    def _format_prompt(self, request: LLMRequest) -> str:
        """Format request messages and tool instructions into a prompt string."""
        prompt_parts: list[str] = []

        system_prompt = request.system or ""
        if request.tools:
            tools_spec = json.dumps(request.tools, indent=2)
            tool_instructions = (
                "\n\nYou have access to the following tools:\n"
                f"{tools_spec}\n\n"
                "To call a tool, respond with a JSON object inside ```json codeblock in the format:\n"
                '{"tool_call": {"name": "<tool_name>", "arguments": {<args>}}}\n'
            )
            system_prompt += tool_instructions

        if system_prompt:
            prompt_parts.append(f"<|system|>\n{system_prompt.strip()}\n<|end|>")

        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                prompt_parts.append(f"<|user|>\n{content}\n<|end|>")
            elif role in ("assistant", "model"):
                prompt_parts.append(f"<|assistant|>\n{content}\n<|end|>")
            elif role == "system":
                prompt_parts.append(f"<|system|>\n{content}\n<|end|>")

        prompt_parts.append("<|assistant|>\n")
        return "\n".join(prompt_parts)

    def _extract_tool_calls(self, text: str) -> tuple[str, list[ToolCall]]:
        """Extract tool calls formatted as JSON blocks from generated text."""
        tool_calls: list[ToolCall] = []
        cleaned_text = text

        pattern = re.compile(r"```(?:json)?\s*(\{\s*\"tool_call\"[\s\S]*?\})\s*```", re.IGNORECASE)
        matches = list(pattern.finditer(text))

        for idx, match in enumerate(matches):
            raw_json = match.group(1)
            try:
                data = json.loads(raw_json)
                if "tool_call" in data:
                    tc = data["tool_call"]
                    name = tc.get("name", "unknown")
                    arguments = tc.get("arguments", {})
                    tool_calls.append(
                        ToolCall(
                            id=f"litert_{name}_{idx}",
                            name=name,
                            arguments=arguments,
                        )
                    )
            except Exception:
                continue

        return cleaned_text, tool_calls

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send completion request to LiteRT-LM in-process engine."""
        async with self._lock:
            return await asyncio.to_thread(self._run_inference, request)

    def _run_inference(self, request: LLMRequest) -> LLMResponse:
        engine = self._init_engine()

        full_text = ""
        if hasattr(engine, "create_conversation"):
            with engine.create_conversation() as conversation:
                if request.system and hasattr(conversation, "set_system_instruction"):
                    conversation.set_system_instruction(request.system)

                user_prompt = self._format_prompt(request)
                if hasattr(conversation, "send_message_async"):
                    for chunk in conversation.send_message_async(user_prompt):
                        if isinstance(chunk, dict) and "content" in chunk:
                            for item in chunk["content"]:
                                if "text" in item:
                                    full_text += item["text"]
                        elif isinstance(chunk, str):
                            full_text += chunk
                elif hasattr(conversation, "send_message"):
                    resp = conversation.send_message(user_prompt)
                    if isinstance(resp, str):
                        full_text = resp
                    elif isinstance(resp, dict) and "text" in resp:
                        full_text = resp["text"]
                    elif hasattr(resp, "text"):
                        full_text = str(resp.text)
        elif hasattr(engine, "generate"):
            prompt = self._format_prompt(request)
            resp = engine.generate(prompt)
            full_text = str(resp)
        else:
            raise RuntimeError("LiteRT-LM engine instance has no supported conversation or generate methods.")

        cleaned_text, tool_calls = self._extract_tool_calls(full_text)

        confidence: float | None = None
        if hasattr(engine, "get_last_confidence"):
            try:
                confidence = float(engine.get_last_confidence())
            except Exception:
                pass

        return LLMResponse(
            content=cleaned_text.strip(),
            tool_calls=tool_calls,
            model=self.model,
            backend="litert",
            confidence=confidence,
        )

    async def is_available(self) -> bool:
        """Check if litert-lm is installed and model target is configured."""
        try:
            import litert_lm  # noqa: F401
        except ImportError:
            return False

        model_path = Path(self.model)
        if model_path.suffix in (".litertlm", ".tflite", ".bin") or "/" in self.model or "\\" in self.model:
            return model_path.exists()

        return bool(self.model)

    def close(self) -> None:
        """Release native LiteRT engine resources."""
        if self._engine is not None:
            if hasattr(self._engine, "close"):
                self._engine.close()
            self._engine = None
