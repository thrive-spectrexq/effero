"""Routes a single LLM call to a local (llama.cpp / Ollama / vLLM) or
cloud backend based on declared needs (latency, tool-calling reliability,
multimodality).

Placeholder module -- concrete backend adapters land in a later milestone.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelRoute:
    """Describes where a single LLM call should be sent.

    This is intentionally minimal for now; it exists so other modules
    have a stable type to import while the real router is built out.
    """

    backend: str
    model: str
    fallback: list[str] | None = None
