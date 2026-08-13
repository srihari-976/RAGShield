"""Backfill: re-classify existing READY documents with the AI access classifier.

Usage (from backend/):
    .venv\\Scripts\\python -m scripts.backfill_classify [tenant_id]

Manual documents (classification_source == 'manual') are skipped so admin
overrides always win. Run this after deploying the auto-classification feature.
"""

import sys

from app.core.database import SessionLocal
from app.ingestion.pipeline import classify_existing_document
from app.models.document import Document

ALL = "__all__"


def main() -> None:
    tenant_filter = sys.argv[1] if len(sys.argv) > 1 else ALL
    db = SessionLocal()
    q = db.query(Document).filter(Document.status == "READY")
    if tenant_filter != ALL:
        q = q.filter(Document.tenant_id == tenant_filter)
    docs = q.all()
    print(f"scanning {len(docs)} READY documents")
    done = skipped = 0
    for doc in docs:
        result = classify_existing_document(db, doc)
        if result is None:
            skipped += 1
            print(f"  - {doc.filename}: SKIPPED (manual or disabled)")
            continue
        done += 1
        print(
            f"  + {doc.filename}: {result.classification} "
            f"(src={result.source}, conf={result.confidence:.2f}, "
            f"needs_review={result.needs_review}, roles={result.roles})"
        )
    print(f"done: {done} classified, {skipped} skipped")
    db.close()


if __name__ == "__main__":
    main()