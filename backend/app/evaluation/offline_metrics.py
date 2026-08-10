"""Offline retrieval metrics: Recall@K, Precision@K, MRR, nDCG."""

import math
from typing import Any


def recall_at_k(retrieved: list[str], expected: set[str], k: int | None = None) -> float:
    r = retrieved[:k] if k else retrieved
    if not expected:
        return 0.0
    return len(set(r) & expected) / len(expected)


def precision_at_k(retrieved: list[str], expected: set[str], k: int | None = None) -> float:
    r = retrieved[:k] if k else retrieved
    if not r:
        return 0.0
    return len(set(r) & expected) / len(r)


def mrr(retrieved: list[str], expected: set[str]) -> float:
    for i, doc_id in enumerate(retrieved, start=1):
        if doc_id in expected:
            return 1.0 / i
    return 0.0


def ndcg(retrieved: list[str], expected: set[str], k: int | None = None) -> float:
    r = retrieved[:k] if k else retrieved
    if not r:
        return 0.0
    dcg = sum(1.0 / math.log2(i + 1) for i, doc_id in enumerate(r, start=1) if doc_id in expected)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(expected), len(r)) + 1))
    return dcg / ideal if ideal > 0 else 0.0


def compute_metrics(retrieved_doc_ids: list[str], expected_doc_ids: list[str], k: int = 5) -> dict[str, float]:
    expected = set(expected_doc_ids)
    return {
        f"recall_at_{k}": round(recall_at_k(retrieved_doc_ids, expected, k), 4),
        f"precision_at_{k}": round(precision_at_k(retrieved_doc_ids, expected, k), 4),
        "mrr": round(mrr(retrieved_doc_ids, expected), 4),
        "ndcg": round(ndcg(retrieved_doc_ids, expected, k), 4),
    }
