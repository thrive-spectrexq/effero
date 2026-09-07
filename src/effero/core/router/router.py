"""Model router for Effero."""

from __future__ import annotations

import logging

from effero.config import ModelConfig
from effero.core.router.base import LLMBackend, LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class ModelRouter:
    """Routes LLM requests to the configured backends with fallback support."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config
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

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send request trying primary and fallbacks in order."""
        errors = []

        for _i, backend in enumerate(self.backends):
            backend_name = backend.__class__.__name__

            if not await backend.is_available():
                errors.append(f"{backend_name} is not available (check installed packages and API keys).")
                continue

            try:
                logger.debug(f"Attempting completion with {backend_name}")
                response = await backend.complete(request)
                return response
            except Exception as e:
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

            # You might want to extract base_url or other settings from config here if available
            return OpenAIBackend(model=model)

        elif provider == "anthropic":
            from effero.core.router.anthropic_backend import AnthropicBackend

            return AnthropicBackend(model=model)

        elif provider in ("google", "gemini"):
            from effero.core.router.google_backend import GoogleBackend

            return GoogleBackend(model=model)

        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
