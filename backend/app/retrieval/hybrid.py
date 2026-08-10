"""Hybrid retrieval: dense (Qdrant) + lexical (BM25) fused with RRF."""

import math
from typing import Any


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]],
    k: int = 60,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """RRF: score = sum(1 / (k + rank)). Operates on chunk_id identity."""
    scores: dict[str, float] = {}
    details: dict[str, dict] = {}
    for rl in ranked_lists:
        for rank, item in enumerate(rl, start=1):
            cid = item["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            if cid not in details:
                details[cid] = item
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    results = []
    for cid, score in ordered:
        item = dict(details[cid])
        item["fusion_score"] = score
        item["score"] = score
        results.append(item)
        if limit and len(results) >= limit:
            break
    return results
