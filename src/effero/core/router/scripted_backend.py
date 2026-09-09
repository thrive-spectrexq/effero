"""Deterministic and scripted LLM backend for testing, evaluation, and offline simulation."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import Any

from effero.core.router.base import LLMBackend, LLMRequest, LLMResponse


class ScriptedBackend(LLMBackend):
    """Deterministic LLM backend that returns predefined or rule-based responses.

    Eliminates ad-hoc stubs and mocks by providing a production-grade, contract-compliant
    backend suitable for offline simulation, unit and integration tests, and benchmarks.
    """

    def __init__(
        self,
        responses: Sequence[LLMResponse | str | Exception]
        | Callable[[LLMRequest], LLMResponse | str | Any]
        | None = None,
        name: str = "scripted",
        model: str = "scripted-model",
        confidence: float | None = 1.0,
        available: bool = True,
        content: str | None = None,
        should_fail: bool = False,
    ) -> None:
        self.name = name
        self.model = model
        self.default_confidence = confidence
        self.available = available
        self.call_count = 0
        self.availability_checks = 0
        self.history: list[LLMRequest] = []
        self.should_fail = should_fail

        if should_fail:
            self._responses: list[LLMResponse | str | Exception] = [
                RuntimeError(f"Scripted backend '{self.name}' failed")
            ]
            self._generator: Callable[[LLMRequest], LLMResponse | str | Any] | None = None
        elif content is not None and responses is None:
            self._responses = [
                LLMResponse(content=content, backend=self.name, model=self.model, confidence=self.default_confidence)
            ]
            self._generator = None
        elif responses is None:
            self._responses = [
                LLMResponse(content="(ok)", backend=self.name, model=self.model, confidence=self.default_confidence)
            ]
            self._generator = None
        elif callable(responses):
            self._responses = []
            self._generator = responses
        else:
            self._responses = list(responses)
            self._generator = None

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        self.history.append(request)

        if not self.available:
            raise RuntimeError(f"Scripted backend '{self.name}' is currently unavailable.")

        if self._generator is not None:
            res = self._generator(request)
            if inspect.isawaitable(res):
                res = await res
            if isinstance(res, LLMResponse):
                return res
            return LLMResponse(
                content=str(res),
                backend=self.name,
                model=self.model,
                confidence=self.default_confidence,
            )

        if not self._responses:
            return LLMResponse(
                content="(done)",
                backend=self.name,
                model=self.model,
                confidence=self.default_confidence,
            )

        idx = min(self.call_count - 1, len(self._responses) - 1)
        item = self._responses[idx]

        if isinstance(item, Exception):
            raise item
        elif isinstance(item, LLMResponse):
            return item
        else:
            return LLMResponse(
                content=str(item),
                backend=self.name,
                model=self.model,
                confidence=self.default_confidence,
            )

    async def is_available(self) -> bool:
        self.availability_checks += 1
        return self.available
