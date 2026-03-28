"""
Core memory module.
Provides short-term (working) and long-term (vector) memory for AGI agents.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np


# Short-Term / Working Memory

@dataclass
class WorkingMemory:
    """Fixed-capacity FIFO buffer — simulates working memory (like human RAM)."""

    capacity: int = 128
    _buffer: deque = field(default_factory=deque, init=False, repr=False)

    def push(self, item: Any) -> None:
        if len(self._buffer) >= self.capacity:
            self._buffer.popleft()
        self._buffer.append(item)

    def retrieve_all(self) -> list[Any]:
        return list(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)


# Long-Term / Vector Memory

@dataclass
class VectorMemory:
    """
    Long-term associative memory backed by FAISS for fast similarity search.
    Stores (embedding, metadata) pairs and retrieves the most relevant ones.
    """

    dim: int = 768
    _index: Any = field(default=None, init=False, repr=False)
    _meta:  list = field(default_factory=list, init=False, repr=False)

    def _init_index(self) -> None:
        try:
            import faiss
            self._index = faiss.IndexFlatL2(self.dim)
        except ImportError:
            raise ImportError("faiss-cpu is required for VectorMemory. Run: pip install faiss-cpu")

    def store(self, embedding: np.ndarray, metadata: Any) -> None:
        if self._index is None:
            self._init_index()
        vec = np.array(embedding, dtype=np.float32).reshape(1, -1)
        self._index.add(vec)
        self._meta.append(metadata)

    def search(self, query: np.ndarray, top_k: int = 5) -> list[tuple[float, Any]]:
        if self._index is None or self._index.ntotal == 0:
            return []
        vec = np.array(query, dtype=np.float32).reshape(1, -1)
        distances, indices = self._index.search(vec, min(top_k, self._index.ntotal))
        return [(float(distances[0][i]), self._meta[indices[0][i]]) for i in range(len(indices[0]))]

    def __len__(self) -> int:
        return 0 if self._index is None else self._index.ntotal
