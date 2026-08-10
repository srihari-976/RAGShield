"""Ingestion pipeline: VALIDATE -> STORE -> EXTRACT -> CHUNK -> EMBED -> INDEX -> READY.

Documents persist until manually deleted. Pipeline runs synchronously for
simplicity (blocking background task for large files is a follow-up)."""

import logging
import time
import uuid
from typing import Any

from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.embeddings.provider import get_embedding_provider
from app.ingestion.chunking import chunk_text
from app.ingestion.extractors import ExtractionError, detect_mime_type, extract_text
from app.models.document import Document, DocumentVersion
from app.retrieval.vector import vector_index
from app.storage.filestore import file_store

logger = logging.getLogger(__name__)
settings = get_settings()


class IngestionError(Exception):
    pass


def run_pipeline(
    db: Session,
    document: Document,
    filename: str,
    content: bytes,
    tenant_id: str,
    created_by: str,
    embedding_model: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> Document:
    """Executes the full ingestion chain for a stored document record."""
    try:
        document.status = "EXTRACTING"
        db.commit()

        extracted = extract_text(filename, content)
        if not extracted.strip():
            raise IngestionError("no text could be extracted from the document")
        extracted_path = file_store.save_extracted(tenant_id, document.id, f"{document.id}.txt", extracted.encode("utf-8"))
        document.storage_path = extracted_path
        db.commit()

        document.status = "CHUNKING"
        db.commit()
        chunks = chunk_text(extracted, document.document_type, chunk_size=chunk_size, overlap=chunk_overlap)
        if not chunks:
            raise IngestionError("document produced no chunks")

        document.status = "EMBEDDING"
        db.commit()
        provider = get_embedding_provider(model=embedding_model)
        vector_index.ensure_collection(provider.dimension())
        vectors = provider.embed_texts([c.text for c in chunks])

        document.status = "INDEXING"
        db.commit()
        points = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{document.id}:{chunk.index}"))
            points.append(
                {
                    "id": point_id,
                    "vector": vector,
                    "payload": {
                        "chunk_id": f"{document.id}:{chunk.index}",
                        "tenant_id": tenant_id,
                        "document_id": document.id,
                        "owner_id": document.owner_id or "",
                        "classification": document.classification,
                        "document_type": document.document_type,
                        "chunk_index": chunk.index,
                        "text": chunk.text,
                    },
                }
            )
        vector_index.upsert_points(points)

        document.status = "READY"
        document.chunk_count = len(chunks)
        db.commit()
        logger.info("document %s indexed with %d chunks", document.id, len(chunks))
        return document
    except Exception as e:
        document.status = "FAILED"
        document.error_message = str(e)[:500]
        db.commit()
        logger.exception("ingestion failed for %s", document.id)
        raise IngestionError(str(e)) from e


def validate_upload(filename: str, content: bytes) -> None:
    from pathlib import Path

    ext = Path(filename).suffix.lower()
    allowed = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".md", ".html", ".htm", ".json", ".csv"}
    if ext not in allowed:
        raise IngestionError(f"unsupported file type {ext or '(none)'}")
    if len(content) > settings.upload_max_mb * 1024 * 1024:
        raise IngestionError(f"file exceeds {settings.upload_max_mb}MB limit")
