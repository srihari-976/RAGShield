"""Retrieval service: ACL-aware hybrid retrieval pipeline.

Security invariant: `authorized_document_ids(identity)` is computed BEFORE
any search; both the Qdrant query filter and the BM25 corpus are restricted
to it. Nothing unauthorized is ever retrieved.
"""

import logging
import time

from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.rbac import Identity
from app.core.config import get_settings
from app.embeddings.provider import get_embedding_provider
from app.models.document import Document
from app.retrieval import acl_filter
from app.retrieval.bm25 import BM25Index
from app.retrieval.hybrid import reciprocal_rank_fusion
from app.retrieval.reranker import OllamaReranker
from app.retrieval.vector import vector_index

logger = logging.getLogger(__name__)
settings = get_settings()


class RetrievalService:
    def __init__(self, db: Session, authz: AuthorizationService, identity: Identity):
        self.db = db
        self.authz = authz
        self.identity = identity

    def _authorized_chunks_for_bm25(self, allowed_ids: set[str]) -> list[dict]:
        docs = (
            self.db.query(Document.id)
            .filter(Document.tenant_id == self.identity.tenant_id, Document.id.in_(allowed_ids))
            .all()
        )
        ids = {d[0] for d in docs}
        if not ids:
            return []
        res = vector_index.client.scroll(
            collection_name=vector_index.collection,
            scroll_filter={
                "must": [
                    {"key": "tenant_id", "match": {"value": self.identity.tenant_id}},
                    {"key": "document_id", "match": {"any": list(ids)}},
                ]
            },
            limit=10000,
            with_payload=True,
        )
        chunks = []
        for point in res[0]:
            payload = point.payload or {}
            chunks.append(
                {
                    "chunk_id": payload.get("chunk_id", str(point.id)),
                    "text": payload.get("text", ""),
                    "payload": payload,
                }
            )
        return chunks

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        score_threshold: float | None = None,
        rerank: bool | None = None,
    ) -> dict:
        top_k = top_k or settings.hybrid_top_k
        rerank = settings.reranker_enabled if rerank is None else rerank
        t0 = time.perf_counter()
        allowed_ids = self.authz.authorized_document_ids(self.identity)
        t_auth = time.perf_counter() - t0

        t0 = time.perf_counter()
        chunks = self._authorized_chunks_for_bm25(allowed_ids)
        t_corpus = time.perf_counter() - t0

        t0 = time.perf_counter()
        dense = vector_index.search(
            vector=get_embedding_provider().embed_text(query),
            tenant_id=self.identity.tenant_id,
            allowed_document_ids=allowed_ids if not self.authz.is_admin(self.identity) else None,
            limit=top_k,
            score_threshold=score_threshold,
        )
        t_dense = time.perf_counter() - t0

        t0 = time.perf_counter()
        bm25_index = BM25Index.build(f"{self.identity.tenant_id}:{len(chunks)}", chunks)
        lexical = bm25_index.search(query, limit=top_k)
        t_bm25 = time.perf_counter() - t0

        fused = reciprocal_rank_fusion([dense, lexical], limit=top_k)

        t0 = time.perf_counter()
        reranker = OllamaReranker(enabled=rerank)
        ranked = reranker.rerank(query, fused, top_k=settings.rerank_top_k)
        t_rerank = time.perf_counter() - t0

        t0 = time.perf_counter()
        allowed_chunks, denied_ids = acl_filter.verify_chunks(self.db, self.authz, self.identity, ranked)
        t_acl = time.perf_counter() - t0

        return {
            "chunks": allowed_chunks,
            "denied_chunk_ids": denied_ids,
            "timings": {
                "authorize_ms": int((t_auth) * 1000),
                "corpus_ms": int(t_corpus * 1000),
                "embed_dense_ms": int(t_dense * 1000),
                "bm25_ms": int(t_bm25 * 1000),
                "rerank_ms": int(t_rerank * 1000),
                "acl_verify_ms": int(t_acl * 1000),
            },
        }
