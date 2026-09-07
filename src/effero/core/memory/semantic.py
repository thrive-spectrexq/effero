"""Semantic memory module for Effero."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

class SemanticMemory:
    """Stub interface for vector-store backed semantic recall.
    
    This feature will be implemented in v0.2 with vector store support.
    """
    
    def store(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        logger.warning("SemanticMemory.store is a stub and will be implemented in v0.2")
        
    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        logger.warning("SemanticMemory.search is a stub and will be implemented in v0.2")
        return []
        
    def clear(self) -> None:
        logger.warning("SemanticMemory.clear is a stub and will be implemented in v0.2")
