"""Tests for ModelRouter."""

from __future__ import annotations

import pytest

from effero.config import ModelConfig
from effero.core.router.base import LLMBackend, LLMRequest, LLMResponse, ToolCall
from effero.core.router.router import ModelRouter


class MockBackend(LLMBackend):
    """Mock LLM backend for testing."""

    def __init__(self, response_text: str = "hello", should_fail: bool = False):
        self.response_text = response_text
        self.should_fail = should_fail
        self.call_count = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("Backend failed")
        return LLMResponse(content=self.response_text, backend="mock")

    async def is_available(self) -> bool:
        return True


class UnavailableBackend(LLMBackend):
    """Backend that reports itself as unavailable."""

    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("Should not be called")

    async def is_available(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_route_to_primary() -> None:
    config = ModelConfig(backend="openai", model="test")
    router = ModelRouter(config)
    # Replace backends with mock
    mock = MockBackend("primary response")
    router.backends = [mock]

    request = LLMRequest(messages=[{"role": "user", "content": "hello"}])
    resp = await router.complete(request)
    assert resp.content == "primary response"
    assert mock.call_count == 1


@pytest.mark.asyncio
async def test_fallback_on_primary_failure() -> None:
    config = ModelConfig(backend="openai", model="test")
    router = ModelRouter(config)
    primary = MockBackend("primary", should_fail=True)
    fallback = MockBackend("fallback response")
    router.backends = [primary, fallback]

    request = LLMRequest(messages=[{"role": "user", "content": "hello"}])
    resp = await router.complete(request)
    assert resp.content == "fallback response"


@pytest.mark.asyncio
async def test_all_backends_fail() -> None:
    config = ModelConfig(backend="openai", model="test")
    router = ModelRouter(config)
    router.backends = [
        MockBackend("a", should_fail=True),
        MockBackend("b", should_fail=True),
    ]

    request = LLMRequest(messages=[{"role": "user", "content": "hello"}])
    with pytest.raises(RuntimeError, match="All LLM backends failed"):
        await router.complete(request)


@pytest.mark.asyncio
async def test_skip_unavailable_backend() -> None:
    config = ModelConfig(backend="openai", model="test")
    router = ModelRouter(config)
    router.backends = [UnavailableBackend(), MockBackend("available")]

    request = LLMRequest(messages=[{"role": "user", "content": "hello"}])
    resp = await router.complete(request)
    assert resp.content == "available"


@pytest.mark.asyncio
async def test_tool_calls_in_response() -> None:
    """Verify ToolCall dataclass works correctly."""
    tc = ToolCall(id="call-1", name="test.skill", arguments={"x": 1})
    resp = LLMResponse(content=None, tool_calls=[tc])
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "test.skill"
    assert resp.tool_calls[0].arguments == {"x": 1}
