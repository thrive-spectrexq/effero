"""Tests for Cactus backend configuration and confidence-based hybrid cloud handoff."""

from __future__ import annotations

import pytest

from effero.config import ModelConfig
from effero.core.router import ScriptedBackend
from effero.core.router.base import LLMRequest
from effero.core.router.openai_backend import OpenAIBackend
from effero.core.router.router import ModelRouter


def test_cactus_backend_factory() -> None:
    """Verify Cactus provider initializes OpenAIBackend with default local endpoint and key."""
    config = ModelConfig(backend="cactus", model="cactus-7b")
    router = ModelRouter(config)
    assert len(router.backends) == 1
    backend = router.backends[0]
    assert isinstance(backend, OpenAIBackend)
    assert backend.model == "cactus-7b"
    assert backend.base_url == "http://127.0.0.1:8080/v1"
    assert backend.api_key == "cactus"


def test_cactus_backend_factory_custom_base_url() -> None:
    """Verify custom base_url and api_key are respected for Cactus provider."""
    config = ModelConfig(
        backend="cactus",
        model="cactus-3b",
        base_url="http://192.168.1.50:8080/v1",
        api_key="custom-cactus-key",
    )
    router = ModelRouter(config)
    backend = router.backends[0]
    assert isinstance(backend, OpenAIBackend)
    assert backend.base_url == "http://192.168.1.50:8080/v1"
    assert backend.api_key == "custom-cactus-key"


@pytest.mark.asyncio
async def test_hybrid_fallback_on_low_confidence() -> None:
    """When primary backend has confidence below threshold, it escalates to cloud fallback."""
    config = ModelConfig(
        backend="cactus",
        model="cactus-7b",
        fallback=["openai:gpt-4o"],
        min_confidence=0.75,
        hybrid_cloud_fallback=True,
    )
    router = ModelRouter(config)

    # Replace backends with mocks
    primary = ScriptedBackend(name="cactus_local", content="unsure local", confidence=0.45)
    fallback = ScriptedBackend(name="cloud_gpt4o", content="confident cloud", confidence=0.95)
    router.backends = [primary, fallback]

    request = LLMRequest(messages=[{"role": "user", "content": "solve complex spatial problem"}])
    response = await router.complete(request)

    assert primary.call_count == 1
    assert fallback.call_count == 1
    assert response.content == "confident cloud"
    assert response.backend == "cloud_gpt4o"
    assert response.confidence == 0.95


@pytest.mark.asyncio
async def test_hybrid_no_fallback_on_high_confidence() -> None:
    """When primary backend has high confidence (>= min_confidence), no cloud escalation occurs."""
    config = ModelConfig(
        backend="cactus",
        model="cactus-7b",
        fallback=["openai:gpt-4o"],
        min_confidence=0.70,
        hybrid_cloud_fallback=True,
    )
    router = ModelRouter(config)

    primary = ScriptedBackend(name="cactus_local", content="fast local answer", confidence=0.88)
    fallback = ScriptedBackend(name="cloud_gpt4o", content="cloud answer", confidence=0.99)
    router.backends = [primary, fallback]

    request = LLMRequest(messages=[{"role": "user", "content": "turn on lights"}])
    response = await router.complete(request)

    assert primary.call_count == 1
    assert fallback.call_count == 0  # Cloud was never invoked!
    assert response.content == "fast local answer"
    assert response.backend == "cactus_local"
    assert response.confidence == 0.88


@pytest.mark.asyncio
async def test_hybrid_disabled_returns_low_confidence() -> None:
    """When hybrid_cloud_fallback is False, low confidence response is returned directly."""
    config = ModelConfig(
        backend="cactus",
        model="cactus-7b",
        fallback=["openai:gpt-4o"],
        min_confidence=0.80,
        hybrid_cloud_fallback=False,
    )
    router = ModelRouter(config)

    primary = ScriptedBackend(name="cactus_local", content="local low conf", confidence=0.30)
    fallback = ScriptedBackend(name="cloud_gpt4o", content="cloud answer", confidence=0.95)
    router.backends = [primary, fallback]

    request = LLMRequest(messages=[{"role": "user", "content": "test"}])
    response = await router.complete(request)

    assert primary.call_count == 1
    assert fallback.call_count == 0
    assert response.content == "local low conf"
    assert response.confidence == 0.30


@pytest.mark.asyncio
async def test_hybrid_last_backend_low_confidence_returned() -> None:
    """If all backends have low confidence, the final fallback response is returned rather than failing."""
    config = ModelConfig(
        backend="cactus",
        model="cactus-7b",
        fallback=["openai:gpt-4o"],
        min_confidence=0.80,
        hybrid_cloud_fallback=True,
    )
    router = ModelRouter(config)

    primary = ScriptedBackend(name="cactus_local", content="local low conf", confidence=0.30)
    fallback = ScriptedBackend(name="cloud_gpt4o", content="cloud low conf", confidence=0.50)
    router.backends = [primary, fallback]

    request = LLMRequest(messages=[{"role": "user", "content": "hard problem"}])
    response = await router.complete(request)

    assert primary.call_count == 1
    assert fallback.call_count == 1
    # Fallback is the last backend, so its response is returned even though confidence < 0.80
    assert response.content == "cloud low conf"
    assert response.backend == "cloud_gpt4o"
