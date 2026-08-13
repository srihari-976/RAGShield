"""Unit tests for the human-review decision (apply_review): the endpoint applies
the reviewer's classification, clears the review flag, records a manual override
and re-provisions the read ACLs to match."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.security import hash_password
from app.ingestion.pipeline import apply_review
from app.models.document import Document, DocumentPermission
from app.models.rbac import Role
from app.models.tenant import Tenant
from app.models.user import User


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine)
    tenant = Tenant(name="TestCo", description="test")
    session.add(tenant)
    session.flush()
    owner_role = Role(name="owner", description="", is_system=True)
    lecturer = Role(name="lecturer", description="", is_system=True)
    student = Role(name="student", description="", is_system=True)
    session.add_all([owner_role, lecturer, student])
    session.flush()
    u1 = User(tenant_id=tenant.id, username="lecturer1", email="l@t.co",
              password_hash=hash_password("password123"), roles=[lecturer])
    u2 = User(tenant_id=tenant.id, username="student1", email="s@t.co",
              password_hash=hash_password("password123"), roles=[student])
    session.add_all([u1, u2])
    session.flush()
    doc = Document(
        tenant_id=tenant.id, title="doc", document_type="text",
        classification="restricted", classification_source="llm",
        classifier_confidence=0.3, needs_review=True,
        filename="doc.txt", mime_type="txt",
        size_bytes=1, storage_path="/tmp/doc.txt", created_by=u1.id,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    yield session, tenant, doc
    session.close()


def _acls(db: Session, doc: Document) -> set[tuple[str, str | None]]:
    return {
        (p.principal_type, p.principal_id)
        for p in db.query(DocumentPermission).filter(DocumentPermission.document_id == doc.id).all()
    }


def test_review_restricted_sets_manual_and_roles(db):
    session, _, doc = db
    apply_review(session, doc, "restricted", ["lecturer"])
    session.commit()
    session.refresh(doc)
    assert doc.classification == "restricted"
    assert doc.classification_source == "manual"
    assert doc.classifier_confidence == 1.0
    assert doc.needs_review is False
    assert _acls(session, doc) == {("role", "lecturer")}


def test_review_public_grants_everyone(db):
    session, _, doc = db
    apply_review(session, doc, "public", [])
    session.commit()
    session.refresh(doc)
    assert doc.classification == "public"
    assert doc.needs_review is False
    assert _acls(session, doc) == {("everyone", None)}


def test_review_internal_grants_all_tenant_roles(db):
    session, tenant, doc = db
    apply_review(session, doc, "internal", [])
    session.commit()
    granted = _acls(session, doc)
    assert ("role", "lecturer") in granted
    assert ("role", "student") in granted


def test_review_restricted_no_roles_is_admin_only(db):
    session, _, doc = db
    apply_review(session, doc, "restricted", [])
    session.commit()
    assert _acls(session, doc) == set()


def test_review_replaces_prior_acl_grants(db):
    session, _, doc = db
    apply_review(session, doc, "restricted", ["student"])
    session.commit()
    session.refresh(doc)
    apply_review(session, doc, "confidential", ["lecturer"])
    session.commit()
    assert _acls(session, doc) == {("role", "lecturer")}
    assert doc.classification == "confidential"
    assert doc.classification_source == "manual"


def test_review_grants_specific_user(db):
    session, _, doc = db
    student = session.query(User).filter(User.username == "student1").first()
    apply_review(session, doc, "restricted", [], [student.id])
    session.commit()
    session.refresh(doc)
    assert _acls(session, doc) == {("user", student.id)}
    assert doc.needs_review is False
