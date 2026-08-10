"""Final authorization verification for retrieved chunks.

The retriever already filters at query time; this is the defense-in-depth
second check: every chunk that reaches the LLM is re-verified against the
authorization engine. Any chunk that fails is dropped here — it never enters
the prompt.
"""

from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.rbac import Identity
from app.models.document import Document

VERIFY_BATCH = 200


def verify_chunks(
    db: Session,
    authz: AuthorizationService,
    identity: Identity,
    chunks: list[dict],
) -> tuple[list[dict], list[str]]:
    """Returns (allowed_chunks, denied_chunk_ids)."""
    if not chunks:
        return [], []
    doc_ids = {c["payload"].get("document_id") for c in chunks}
    docs = {
        d.id: d
        for d in db.query(Document)
        .filter(Document.tenant_id == identity.tenant_id, Document.id.in_(doc_ids))
        .all()
    }
    allowed: list[dict] = []
    denied: list[str] = []
    for c in chunks:
        doc = docs.get(c["payload"].get("document_id"))
        if doc is None:
            denied.append(c["chunk_id"])
            continue
        decision = authz.can_read_document(identity, doc)
        if decision.allowed:
            allowed.append(c)
        else:
            denied.append(c["chunk_id"])
    return allowed, denied
