from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.tenant import new_uuid, utcnow

DOCUMENT_STATUSES = ("UPLOADING", "EXTRACTING", "CHUNKING", "EMBEDDING", "INDEXING", "READY", "FAILED", "DELETING")
CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), default="general")
    owner_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    classification: Mapped[str] = mapped_column(String(20), default="internal")
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(String(600), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="UPLOADING")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    tenant = relationship("Tenant", back_populates="documents")
    owner = relationship("User", foreign_keys=[owner_id])
    permissions = relationship("DocumentPermission", back_populates="document", cascade="all, delete-orphan")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(String(32), ForeignKey("documents.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(600), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document = relationship("Document", back_populates="versions")


class DocumentPermission(Base):
    __tablename__ = "document_permissions"
    __table_args__ = (UniqueConstraint("document_id", "principal_type", "principal_id", name="uq_doc_principal"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(String(32), ForeignKey("documents.id"), index=True)
    action: Mapped[str] = mapped_column(String(20), default="read")
    principal_type: Mapped[str] = mapped_column(String(20))  # "user" | "role" | "everyone"
    principal_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    document = relationship("Document", back_populates="permissions")


class ResourcePolicy(Base):
    """ABAC policy: JSON rule evaluated against subject/resource attributes."""

    __tablename__ = "resource_policies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    action: Mapped[str] = mapped_column(String(20), default="read")
    rule: Mapped[str] = mapped_column(Text, nullable=False)  # JSON rule
    effect: Mapped[str] = mapped_column(String(10), default="allow")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
