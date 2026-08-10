"""Admin document management: upload, list, view, search, delete, re-index.
Documents persist until manually deleted (no auto-expiry)."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.dependencies import get_authz_service, get_current_user
from app.auth.rbac import Identity
from app.core.database import get_db
from app.ingestion.pipeline import IngestionError, run_pipeline, validate_upload
from app.models.document import Document, DocumentVersion
from app.observability.audit import log_action
from app.retrieval.vector import vector_index
from app.schemas.schemas import DocumentCreate, DocumentSummary
from app.storage.filestore import file_store

router = APIRouter(prefix="/admin/documents", tags=["admin-documents"])


def _summary(d: Document) -> DocumentSummary:
    return DocumentSummary(
        id=d.id,
        tenant_id=d.tenant_id,
        title=d.title,
        document_type=d.document_type,
        owner_id=d.owner_id,
        classification=d.classification,
        filename=d.filename,
        mime_type=d.mime_type,
        size_bytes=d.size_bytes,
        status=d.status,
        error_message=d.error_message,
        chunk_count=d.chunk_count,
        version=d.version,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def _admin_or_raise(identity: Identity, authz: AuthorizationService) -> None:
    if not authz.is_admin(identity):
        raise HTTPException(status_code=403, detail="admin access required")


def _perm_or_raise(authz: AuthorizationService, identity: Identity, perm: str) -> None:
    if not authz.is_admin(identity) and not authz.can(identity, perm).allowed:
        raise HTTPException(status_code=403, detail=f"{perm} required")


@router.post("/upload", response_model=DocumentSummary, status_code=201)
def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    document_type: str = Form("general"),
    classification: str = Form("internal"),
    owner_id: str | None = Form(None),
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _perm_or_raise(authz, identity, "document.upload")
    content = file.file.read()
    try:
        validate_upload(file.filename, content)
    except IngestionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    doc = Document(
        tenant_id=identity.tenant_id,
        title=title or file.filename,
        document_type=document_type,
        owner_id=owner_id or identity.user_id,
        classification=classification,
        filename=file.filename,
        mime_type=file.filename.split(".")[-1].lower() or "bin",
        size_bytes=len(content),
        storage_path="",
        created_by=identity.user_id,
    )
    db.add(doc)
    db.flush()
    doc.storage_path = file_store.save_original(identity.tenant_id, doc.id, file.filename, content)
    db.add(
        DocumentVersion(
            document_id=doc.id,
            version=1,
            storage_path=doc.storage_path,
            size_bytes=len(content),
            checksum=file_store.checksum(content),
            created_by=identity.user_id,
        )
    )
    db.commit()
    log_action(db, identity.tenant_id, "document.upload", user_id=identity.user_id, resource_type="document", resource_id=doc.id)

    try:
        run_pipeline(db, doc, file.filename, content, identity.tenant_id, identity.user_id)
    except IngestionError as e:
        db.refresh(doc)
        raise HTTPException(status_code=500, detail=f"ingestion failed: {str(e)}") from e
    db.refresh(doc)
    return _summary(doc)


@router.get("", response_model=list[DocumentSummary])
def list_documents(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _perm_or_raise(authz, identity, "document.read")
    docs = db.query(Document).filter(Document.tenant_id == identity.tenant_id).order_by(Document.created_at.desc()).all()
    return [_summary(d) for d in docs if authz.can_read_document(identity, d).allowed]


@router.get("/{document_id}", response_model=DocumentSummary)
def get_document(
    document_id: str,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _perm_or_raise(authz, identity, "document.read")
    doc = db.query(Document).filter(Document.id == document_id, Document.tenant_id == identity.tenant_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    return _summary(doc)


@router.patch("/{document_id}", response_model=DocumentSummary)
def update_document(
    document_id: str,
    body: DocumentCreate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _perm_or_raise(authz, identity, "document.manage")
    doc = db.query(Document).filter(Document.id == document_id, Document.tenant_id == identity.tenant_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            setattr(doc, k, v)
    db.commit()
    db.refresh(doc)
    return _summary(doc)


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: str,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _perm_or_raise(authz, identity, "document.delete")
    doc = db.query(Document).filter(Document.id == document_id, Document.tenant_id == identity.tenant_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    doc.status = "DELETING"
    db.commit()
    try:
        vector_index.delete_document(doc.id)
        file_store.delete_document(identity.tenant_id, doc.id)
        db.delete(doc)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"delete failed: {e}") from e
    log_action(db, identity.tenant_id, "document.delete", user_id=identity.user_id, resource_type="document", resource_id=document_id)


@router.post("/{document_id}/reindex", response_model=DocumentSummary)
def reindex_document(
    document_id: str,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _perm_or_raise(authz, identity, "document.manage")
    doc = db.query(Document).filter(Document.id == document_id, Document.tenant_id == identity.tenant_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    content = file_store.read(doc.storage_path) if doc.storage_path else None
    if content is None:
        raise HTTPException(status_code=500, detail="original file missing")
    vector_index.delete_document(doc.id)
    doc.status = "UPLOADING"
    db.commit()
    run_pipeline(db, doc, doc.filename, content, identity.tenant_id, identity.user_id)
    db.refresh(doc)
    return _summary(doc)


@router.post("/{document_id}/replace", response_model=DocumentSummary)
def replace_document(
    document_id: str,
    file: UploadFile = File(...),
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    """Replaces the stored file of an existing document and re-ingests it,
    bumping the version and keeping the document id and ACLs intact."""
    _perm_or_raise(authz, identity, "document.manage")
    doc = db.query(Document).filter(Document.id == document_id, Document.tenant_id == identity.tenant_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    content = file.file.read()
    try:
        validate_upload(file.filename, content)
    except IngestionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    doc.filename = file.filename
    doc.mime_type = file.filename.split(".")[-1].lower() or "bin"
    doc.size_bytes = len(content)
    doc.storage_path = file_store.save_original(identity.tenant_id, doc.id, file.filename, content)
    doc.version += 1
    db.add(
        DocumentVersion(
            document_id=doc.id,
            version=doc.version,
            storage_path=doc.storage_path,
            size_bytes=len(content),
            checksum=file_store.checksum(content),
            created_by=identity.user_id,
        )
    )
    db.commit()
    log_action(db, identity.tenant_id, "document.replace", user_id=identity.user_id, resource_type="document", resource_id=doc.id,
               metadata={"filename": file.filename, "version": doc.version})
    vector_index.delete_document(doc.id)
    doc.status = "UPLOADING"
    db.commit()
    try:
        run_pipeline(db, doc, doc.filename, content, identity.tenant_id, identity.user_id)
    except IngestionError as e:
        db.refresh(doc)
        raise HTTPException(status_code=500, detail=f"ingestion failed: {str(e)}") from e
    db.refresh(doc)
    return _summary(doc)


@router.get("/search/query")
def search_documents(
    q: str,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    docs = db.query(Document).filter(
        Document.tenant_id == identity.tenant_id,
        Document.title.ilike(f"%{q}%"),
    ).all()
    return [_summary(d) for d in docs]
