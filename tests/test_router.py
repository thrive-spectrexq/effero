"""Tests for ModelRouter."""

from __future__ import annotations

import pytest

from effero.config import ModelConfig
from effero.core.router import ScriptedBackend
from effero.core.router.base import LLMRequest, LLMResponse, ToolCall
from effero.core.router.router import ModelRouter


@pytest.mark.asyncio
async def test_route_to_primary() -> None:
    config = ModelConfig(backend="openai", model="test")
    router = ModelRouter(config)
    primary = ScriptedBackend(content="primary response")
    router.backends = [primary]

    request = LLMRequest(messages=[{"role": "user", "content": "hello"}])
    resp = await router.complete(request)
    assert resp.content == "primary response"
    assert primary.call_count == 1


@pytest.mark.asyncio
async def test_fallback_on_primary_failure() -> None:
    config = ModelConfig(backend="openai", model="test")
    router = ModelRouter(config)
    primary = ScriptedBackend(content="primary", should_fail=True)
    fallback = ScriptedBackend(content="fallback response")
    router.backends = [primary, fallback]

    request = LLMRequest(messages=[{"role": "user", "content": "hello"}])
    resp = await router.complete(request)
    assert resp.content == "fallback response"


@pytest.mark.asyncio
async def test_all_backends_fail() -> None:
    config = ModelConfig(backend="openai", model="test")
    router = ModelRouter(config)
    router.backends = [
        ScriptedBackend(content="a", should_fail=True),
        ScriptedBackend(content="b", should_fail=True),
    ]

    request = LLMRequest(messages=[{"role": "user", "content": "hello"}])
    with pytest.raises(RuntimeError, match="All LLM backends failed"):
        await router.complete(request)


@pytest.mark.asyncio
async def test_skip_unavailable_backend() -> None:
    config = ModelConfig(backend="openai", model="test")
    router = ModelRouter(config)
    router.backends = [ScriptedBackend(available=False), ScriptedBackend(content="available")]

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


@pytest.mark.asyncio
async def test_availability_caching() -> None:
    config = ModelConfig(backend="openai", model="test")
    router = ModelRouter(config)
    counting = ScriptedBackend(content="ok", name="counting")
    router.backends = [counting]

    request = LLMRequest(messages=[{"role": "user", "content": "test"}])
    for _ in range(5):
        await router.complete(request)

    # complete() was called 5 times, but is_available() should only be called once due to caching!
    assert counting.call_count == 5
    assert counting.availability_checks == 1


def test_router_scripted_factory() -> None:
    """Verify ModelRouter creates ScriptedBackend for scripted/deterministic provider."""
    for provider in ("scripted", "deterministic", "mock"):
        config = ModelConfig(backend=provider, model="eval-v1")
        router = ModelRouter(config)
        assert len(router.backends) == 1
        assert isinstance(router.backends[0], ScriptedBackend)
        assert router.backends[0].model == "eval-v1"
