"""Model router for Effero."""

from __future__ import annotations

import logging
import time

from effero.config import ModelConfig
from effero.core.router.base import LLMBackend, LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class ModelRouter:
    """Routes LLM requests to the configured backends with fallback support and cached availability."""

    def __init__(self, config: ModelConfig, availability_cache_ttl: float = 300.0) -> None:
        self.config = config
        self.availability_cache_ttl = availability_cache_ttl
        self._availability_cache: dict[int, tuple[bool, float]] = {}
        self.backends: list[LLMBackend] = []

        # Primary backend
        primary = self._create_backend(config.backend, config.model, config)
        self.backends.append(primary)

        # Fallback backends
        if config.fallback:
            for fb in config.fallback:
                if ":" in fb:
                    provider, model = fb.split(":", 1)
                else:
                    provider, model = fb, config.model
                fallback_backend = self._create_backend(provider, model, config)
                self.backends.append(fallback_backend)

    async def _check_backend_available(self, backend: LLMBackend) -> bool:
        """Check availability with TTL caching to prevent repeated network health checks."""
        backend_id = id(backend)
        now = time.time()
        if backend_id in self._availability_cache:
            is_avail, cached_at = self._availability_cache[backend_id]
            ttl = self.availability_cache_ttl if is_avail else 30.0
            if (now - cached_at) < ttl:
                return is_avail

        is_avail = await backend.is_available()
        self._availability_cache[backend_id] = (is_avail, now)
        return is_avail

    def clear_availability_cache(self) -> None:
        """Clear cached availability status for all backends."""
        self._availability_cache.clear()

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send request trying primary and fallbacks in order."""
        errors = []

        for _i, backend in enumerate(self.backends):
            backend_name = backend.__class__.__name__

            if not await self._check_backend_available(backend):
                errors.append(f"{backend_name} is not available (check installed packages and API keys).")
                continue

            try:
                logger.debug(f"Attempting completion with {backend_name}")
                response = await backend.complete(request)
                # Mark backend as confirmed available
                self._availability_cache[id(backend)] = (True, time.time())

                # Check for hybrid cloud handoff (confidence-based escalation)
                if (
                    self.config.hybrid_cloud_fallback
                    and _i < len(self.backends) - 1
                    and response.confidence is not None
                    and response.confidence < self.config.min_confidence
                ):
                    msg = (
                        f"{backend_name} confidence ({response.confidence:.2f}) is below threshold "
                        f"({self.config.min_confidence:.2f}). Escalating to fallback backend..."
                    )
                    logger.info(msg)
                    errors.append(msg)
                    continue

                return response
            except Exception as e:
                # Evict from cache on error so subsequent requests can re-evaluate
                self._availability_cache.pop(id(backend), None)
                msg = f"{backend_name} error: {e}"
                logger.warning(msg)
                errors.append(msg)

        # If we got here, all backends failed
        error_msgs = "\n".join(f" - {err}" for err in errors)
        raise RuntimeError(f"All LLM backends failed:\n{error_msgs}")

    @staticmethod
    def _create_backend(provider: str, model: str, config: ModelConfig) -> LLMBackend:
        """Factory method to create backend instances."""
        provider = provider.lower()

        if provider == "openai":
            from effero.core.router.openai_backend import OpenAIBackend

            return OpenAIBackend(model=model, api_key=config.api_key, base_url=config.base_url)

        elif provider in ("ollama", "local", "llama.cpp", "llamacpp"):
            from effero.core.router.openai_backend import OpenAIBackend

            # Ollama and llama.cpp expose standard OpenAI-compatible /v1 endpoints
            base_url = config.base_url or "http://127.0.0.1:11434/v1"
            api_key = config.api_key or "ollama"
            return OpenAIBackend(model=model, api_key=api_key, base_url=base_url)

        elif provider == "cactus":
            from effero.core.router.openai_backend import OpenAIBackend

            # Cactus exposes an ultra-fast on-device OpenAI-compatible local server
            base_url = config.base_url or "http://127.0.0.1:8080/v1"
            api_key = config.api_key or "cactus"
            return OpenAIBackend(model=model, api_key=api_key, base_url=base_url)

        elif provider == "anthropic":
            from effero.core.router.anthropic_backend import AnthropicBackend

            return AnthropicBackend(model=model, api_key=config.api_key)

        elif provider in ("google", "gemini"):
            from effero.core.router.google_backend import GoogleBackend

            return GoogleBackend(model=model, api_key=config.api_key)

        elif provider in ("litert", "litert-lm", "litertlm"):
            from effero.core.router.litert_backend import LiteRTLMBackend

            return LiteRTLMBackend(model=model, device=config.device)

        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
