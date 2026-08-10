"""BM25 lexical retrieval over the authorized chunk corpus.

The corpus is always pre-filtered to the current user's authorized document
ids — unauthorized chunks never enter the index.
"""

import re
from typing import Any

from rank_bm25 import BM25Okapi

_WORD_RE = re.compile(r"[A-Za-z0-9_\-$₹€.]+")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


class BM25Index:
    """Corpus-level BM25. Rebuilt per request from authorized chunks (cached by key)."""

    _cache: dict[str, "BM25Index"] = {}

    def __init__(self, chunks: list[dict[str, Any]]):
        self.chunks = chunks
        tokenized = [_tokenize(c["text"]) for c in chunks]
        self.bm25 = BM25Okapi(tokenized) if tokenized else None

    @classmethod
    def build(cls, key: str, chunks: list[dict[str, Any]]) -> "BM25Index":
        if key not in cls._cache or len(cls._cache) > 16:
            cls._cache = {}
        index = cls(chunks)
        cls._cache[key] = index
        return index

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        if not self.bm25 or not self.chunks:
            return []
        scores = self.bm25.get_scores(_tokenize(query))
        ranked = sorted(zip(self.chunks, scores), key=lambda x: x[1], reverse=True)
        results = [
            {"chunk_id": c["chunk_id"], "score": float(s), "payload": c.get("payload", {})}
            for c, s in ranked[:limit]
            if s > 0
        ]
        return results
