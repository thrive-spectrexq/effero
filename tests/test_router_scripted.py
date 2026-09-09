"""Tests for ScriptedBackend deterministic execution, generator callbacks, and error handling."""

from __future__ import annotations

import pytest

from effero.core.router import ScriptedBackend
from effero.core.router.base import LLMRequest, LLMResponse, ToolCall


@pytest.mark.asyncio
async def test_scripted_backend_sequential_responses() -> None:
    backend = ScriptedBackend(
        responses=[
            "First response",
            LLMResponse(content="Second response", confidence=0.85),
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id="tc_1", name="robotics.arm.move", arguments={"x": 1.0})],
            ),
        ]
    )

    req = LLMRequest(messages=[{"role": "user", "content": "ping"}])
    r1 = await backend.complete(req)
    assert r1.content == "First response"
    assert backend.call_count == 1

    r2 = await backend.complete(req)
    assert r2.content == "Second response"
    assert r2.confidence == 0.85

    r3 = await backend.complete(req)
    assert len(r3.tool_calls) == 1
    assert r3.tool_calls[0].name == "robotics.arm.move"

    # Beyond sequence length, repeats last response
    r4 = await backend.complete(req)
    assert len(r4.tool_calls) == 1


@pytest.mark.asyncio
async def test_scripted_backend_dynamic_generator() -> None:
    def generator(req: LLMRequest) -> str:
        last_msg = req.messages[-1].get("content", "")
        return f"Echo: {last_msg}"

    backend = ScriptedBackend(responses=generator)
    req = LLMRequest(messages=[{"role": "user", "content": "Hello Effero"}])
    resp = await backend.complete(req)
    assert resp.content == "Echo: Hello Effero"


@pytest.mark.asyncio
async def test_scripted_backend_exception_handling() -> None:
    backend = ScriptedBackend(responses=[ValueError("Simulated rate limit error")])
    req = LLMRequest(messages=[{"role": "user", "content": "test"}])
    with pytest.raises(ValueError, match="Simulated rate limit error"):
        await backend.complete(req)


@pytest.mark.asyncio
async def test_scripted_backend_availability() -> None:
    backend = ScriptedBackend(available=False)
    assert await backend.is_available() is False
    req = LLMRequest(messages=[{"role": "user", "content": "test"}])
    with pytest.raises(RuntimeError, match="unavailable"):
        await backend.complete(req)
