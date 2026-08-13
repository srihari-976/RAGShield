"""Unit tests for ACL provisioning based on classifier decisions."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.ingestion.classifier import ClassificationResult
from app.ingestion.pipeline import provision_access, tenant_role_names
from app.models.document import Document, DocumentPermission
from app.models.rbac import Role
from app.models.tenant import Tenant
from app.models.user import User
from app.core.security import hash_password


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
        classification="internal", filename="doc.txt", mime_type="txt",
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


def test_internal_grants_all_tenant_roles(db):
    session, tenant, doc = db
    provision_access(session, doc, ClassificationResult("internal", [], 0.9, "heuristic"), tenant.id)
    session.commit()
    granted = _acls(session, doc)
    assert ("role", "lecturer") in granted
    assert ("role", "student") in granted
    # owner role has no user in this fixture tenant, so it is not granted
    assert ("role", "owner") not in granted


def test_public_grants_everyone(db):
    session, tenant, doc = db
    provision_access(session, doc, ClassificationResult("public", [], 0.9, "heuristic"), tenant.id)
    session.commit()
    granted = _acls(session, doc)
    assert ("everyone", None) in granted
    assert len(granted) == 1


def test_restricted_grants_only_named_roles(db):
    session, tenant, doc = db
    provision_access(session, doc, ClassificationResult("restricted", ["lecturer"], 0.95, "heuristic"), tenant.id)
    session.commit()
    granted = _acls(session, doc)
    assert ("role", "lecturer") in granted
    assert ("role", "student") not in granted
    assert ("everyone", None) not in granted


def test_restricted_with_no_roles_grants_nothing(db):
    session, tenant, doc = db
    provision_access(session, doc, ClassificationResult("restricted", [], 0.9, "heuristic"), tenant.id)
    session.commit()
    assert _acls(session, doc) == set()


def test_provision_replaces_previous_acls(db):
    session, tenant, doc = db
    provision_access(session, doc, ClassificationResult("internal", [], 0.9, "heuristic"), tenant.id)
    provision_access(session, doc, ClassificationResult("restricted", ["student"], 0.95, "heuristic"), tenant.id)
    session.commit()
    granted = _acls(session, doc)
    assert granted == {("role", "student")}


def test_tenant_role_names_only_active_users(db):
    session, tenant, _doc = db
    names = tenant_role_names(session, tenant.id)
    assert names == ["lecturer", "student"]


def test_restricted_subject_resolves_to_user_acl(db):
    session, tenant, doc = db
    lecturer = session.query(User).filter(User.username == "lecturer1").first()
    res = ClassificationResult("restricted", [], 0.95, "filename", subject="lecturer1")
    provision_access(session, doc, res, tenant.id)
    session.commit()
    session.refresh(doc)
    granted = _acls(session, doc)
    assert ("user", lecturer.id) in granted
    assert doc.needs_review is False


def test_restricted_subject_unmatched_flags_review(db):
    session, tenant, doc = db
    res = ClassificationResult("restricted", [], 0.95, "filename", subject="ghost-person")
    provision_access(session, doc, res, tenant.id)
    session.commit()
    session.refresh(doc)
    assert _acls(session, doc) == set()
    assert doc.needs_review is True


def test_restricted_no_grants_flags_review(db):
    session, tenant, doc = db
    provision_access(session, doc, ClassificationResult("restricted", [], 0.9, "heuristic"), tenant.id)
    session.commit()
    session.refresh(doc)
    assert _acls(session, doc) == set()
    assert doc.needs_review is True