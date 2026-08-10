"""User-facing routes: profile, my documents, conversations."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.dependencies import get_authz_service, get_current_user
from app.auth.rbac import Identity
from app.core.database import get_db
from app.models.chat import Conversation
from app.models.document import Document
from app.schemas.schemas import DocumentSummary

router = APIRouter(tags=["user"])


def _doc_summary(d: Document) -> DocumentSummary:
    return DocumentSummary(
        id=d.id, tenant_id=d.tenant_id, title=d.title, document_type=d.document_type,
        owner_id=d.owner_id, classification=d.classification, filename=d.filename,
        mime_type=d.mime_type, size_bytes=d.size_bytes, status=d.status,
        error_message=d.error_message, chunk_count=d.chunk_count, version=d.version,
        created_at=d.created_at, updated_at=d.updated_at,
    )


@router.get("/profile/documents", response_model=list[DocumentSummary])
def my_documents(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    docs = (
        db.query(Document)
        .filter(Document.tenant_id == identity.tenant_id, Document.owner_id == identity.user_id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return [_doc_summary(d) for d in docs]


@router.get("/profile/conversations", response_model=list[dict])
def my_conversations(
    identity: Identity = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == identity.user_id, Conversation.tenant_id == identity.tenant_id)
        .order_by(Conversation.updated_at.desc())
        .limit(20)
        .all()
    )
    return [
        {"id": c.id, "title": c.title, "model": c.model, "rag_version": c.rag_version, "created_at": c.created_at.isoformat()}
        for c in rows
    ]
