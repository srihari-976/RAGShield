"""Qdrant indexer. Single collection; every point carries mandatory security
payload (tenant_id, document_id, owner_id, classification) so retrieval can
filter by authorization at query time.
"""

import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class VectorIndex:
    def __init__(self, url: str | None = None, collection: str | None = None):
        self.client = QdrantClient(url=url or settings.qdrant_url)
        self.collection = collection or settings.qdrant_collection

    def ensure_collection(self, dim: int) -> None:
        existing = self.client.get_collections().collections
        if self.collection not in {c.name for c in existing}:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
            )
            logger.info("created collection %s dim=%d", self.collection, dim)

    def upsert_points(self, points: list[dict[str, Any]]) -> None:
        if not points:
            return
        payloads = [
            qm.PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points
        ]
        self.client.upsert(collection_name=self.collection, points=payloads)

    def delete_document(self, document_id: str) -> int:
        res = self.client.delete(
            collection_name=self.collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=document_id))])
            ),
        )
        return getattr(res, "status", None) == "ok"

    def search(
        self,
        vector: list[float],
        tenant_id: str,
        allowed_document_ids: set[str] | None,
        limit: int,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        must: list = [qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tenant_id))]
        if allowed_document_ids is not None:
            must.append(qm.FieldCondition(key="document_id", match=qm.MatchAny(any=list(allowed_document_ids))))
        res = self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            query_filter=qm.Filter(must=must),
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return [
            {"id": hit.id, "chunk_id": (hit.payload or {}).get("chunk_id", str(hit.id)), "score": hit.score, "payload": hit.payload}
            for hit in res
        ]

    def count_documents(self, tenant_id: str) -> int:
        res = self.client.count(
            collection_name=self.collection,
            count_filter=qm.Filter(must=[qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tenant_id))]),
        )
        return res.count


vector_index = VectorIndex()
