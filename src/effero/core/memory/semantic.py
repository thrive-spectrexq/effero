"""Semantic vector memory module for Effero."""

from __future__ import annotations

import json
import logging
import math
import time
import uuid
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MemoryRecord:
    """A single piece of remembered knowledge with vector representation."""

    id: str
    text: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "embedding": self.embedding,
            "metadata": self.metadata,
            "score": self.score,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryRecord:
        return cls(
            id=data["id"],
            text=data["text"],
            embedding=data.get("embedding", []),
            metadata=data.get("metadata", {}),
            score=data.get("score", 0.0),
            timestamp=data.get("timestamp", time.time()),
        )


class EmbeddingProvider(ABC):
    """Abstract interface for text embedding models."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Compute dense vector representation for a text snippet."""
        ...


class LightweightTFIDFEmbedding(EmbeddingProvider):
    """Zero-dependency hash-based n-gram embedding with L2 normalization.

    Provides reliable semantic and lexical similarity search out of the box
    without requiring external model weights, torch, or API tokens.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        import hashlib

        tokens = [t.strip().lower() for t in text.split() if t.strip()]
        if not tokens:
            return [0.0] * self.dim

        vec = [0.0] * self.dim
        # Word unigrams + subword character trigrams for typo resilience
        features = tokens.copy()
        for token in tokens:
            if len(token) >= 3:
                for i in range(len(token) - 2):
                    features.append(token[i : i + 3])

        counts = Counter(features)
        for feat, count in counts.items():
            digest = hashlib.md5(feat.encode("utf-8")).digest()
            h = int.from_bytes(digest[:4], "little") % self.dim
            vec[h] += float(count)

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two unit-normalized vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    return max(0.0, min(1.0, dot))


class SemanticMemory:
    """Vector-store backed semantic recall memory.

    Stores knowledge chunks, actions, and observations, enabling nearest-neighbor
    semantic search to retrieve contextually relevant memories for planning.
    """

    def __init__(
        self,
        embedder: EmbeddingProvider | None = None,
        persistence_path: str | Path | None = None,
    ):
        self.embedder: EmbeddingProvider = embedder or LightweightTFIDFEmbedding()
        self.persistence_path = Path(persistence_path) if persistence_path else None
        self._records: dict[str, MemoryRecord] = {}

        if self.persistence_path and self.persistence_path.exists():
            self.load()

    def store(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        record_id: str | None = None,
    ) -> str:
        """Store a text snippet and its metadata in semantic vector memory."""
        rec_id = record_id or str(uuid.uuid4())
        vec = self.embedder.embed(text)
        record = MemoryRecord(
            id=rec_id,
            text=text,
            embedding=vec,
            metadata=metadata or {},
        )
        self._records[rec_id] = record

        if self.persistence_path:
            self.save()

        return rec_id

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[MemoryRecord]:
        """Search memory for records most similar to the query."""
        if not self._records or not query.strip():
            return []

        query_vec = self.embedder.embed(query)
        scored: list[MemoryRecord] = []

        for record in self._records.values():
            if filter_metadata:
                match = all(record.metadata.get(k) == v for k, v in filter_metadata.items())
                if not match:
                    continue

            sim = cosine_similarity(query_vec, record.embedding)
            if sim >= min_score:
                rec_copy = MemoryRecord(
                    id=record.id,
                    text=record.text,
                    embedding=record.embedding,
                    metadata=record.metadata,
                    score=sim,
                    timestamp=record.timestamp,
                )
                scored.append(rec_copy)

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def delete(self, record_id: str) -> bool:
        """Delete a record by ID."""
        if record_id in self._records:
            del self._records[record_id]
            if self.persistence_path:
                self.save()
            return True
        return False

    def clear(self) -> None:
        """Clear all stored semantic memories."""
        self._records.clear()
        if self.persistence_path and self.persistence_path.exists():
            try:
                self.persistence_path.unlink()
            except OSError as e:
                logger.error(f"Error removing memory persistence file: {e}")

    def count(self) -> int:
        """Total number of stored memory records."""
        return len(self._records)

    def save(self, path: str | Path | None = None) -> None:
        """Persist memory records to JSON file."""
        target = Path(path) if path else self.persistence_path
        if not target:
            return

        target.parent.mkdir(parents=True, exist_ok=True)
        data = [r.to_dict() for r in self._records.values()]
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self, path: str | Path | None = None) -> None:
        """Load memory records from JSON file."""
        target = Path(path) if path else self.persistence_path
        if not target or not target.exists():
            return

        try:
            content = target.read_text(encoding="utf-8")
            data = json.loads(content)
            self._records = {item["id"]: MemoryRecord.from_dict(item) for item in data}
        except Exception as e:
            logger.error(f"Failed to load semantic memory from {target}: {e}")
