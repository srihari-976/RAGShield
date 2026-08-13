"""Regression tests: authorized_document_ids must never leak documents from
other tenants, even when an `everyone`/role/user ACL exists on a cross-tenant
document."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.rbac import Identity
from app.core.database import Base
from app.core.security import hash_password
from app.models.document import Document, DocumentPermission
from app.models.rbac import Role
from app.models.tenant import Tenant
from app.models.user import User


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine)
    t_a = Tenant(name="TenantA", description="")
    t_b = Tenant(name="TenantB", description="")
    session.add_all([t_a, t_b])
    session.flush()

    employee = Role(name="employee", description="", is_system=True)
    owner = Role(name="owner", description="", is_system=True)
    session.add_all([employee, owner])
    session.flush()

    u_a = User(tenant_id=t_a.id, username="alice", email="alice@a.co",
               password_hash=hash_password("password123"), roles=[employee])
    session.add(u_a)
    session.flush()

    # a PUBLIC (everyone) document in the OTHER tenant
    doc_b = Document(
        tenant_id=t_b.id, title="Syllabus B", document_type="text", classification="public",
        filename="syllabus.txt", mime_type="txt", size_bytes=1,
        storage_path="/tmp/b.txt", created_by=u_a.id,
    )
    session.add(doc_b)
    session.flush()
    session.add(DocumentPermission(document_id=doc_b.id, action="read", principal_type="everyone", principal_id=None))
    # and a role grant on a second cross-tenant doc
    doc_b2 = Document(
        tenant_id=t_b.id, title="Role Doc B", document_type="text", classification="restricted",
        filename="b2.txt", mime_type="txt", size_bytes=1,
        storage_path="/tmp/b2.txt", created_by=u_a.id,
    )
    session.add(doc_b2)
    session.flush()
    session.add(DocumentPermission(document_id=doc_b2.id, action="read", principal_type="role", principal_id="employee"))

    session.commit()
    yield session, t_a, t_b, u_a, doc_b, doc_b2
    session.close()


def test_no_cross_tenant_leak_via_everyone_acl(db):
    session, t_a, _t_b, u_a, doc_b, _doc_b2 = db
    authz = AuthorizationService(session)
    identity = Identity(user_id=u_a.id, tenant_id=t_a.id, username="alice", roles=["employee"], permissions=set())
    allowed = authz.authorized_document_ids(identity)
    assert doc_b.id not in allowed


def test_no_cross_tenant_leak_via_role_acl(db):
    session, t_a, _t_b, u_a, _doc_b, doc_b2 = db
    authz = AuthorizationService(session)
    identity = Identity(user_id=u_a.id, tenant_id=t_a.id, username="alice", roles=["employee"], permissions=set())
    allowed = authz.authorized_document_ids(identity)
    assert doc_b2.id not in allowed


def test_can_read_document_still_blocks_cross_tenant(db):
    session, t_a, _t_b, u_a, doc_b, _doc_b2 = db
    authz = AuthorizationService(session)
    identity = Identity(user_id=u_a.id, tenant_id=t_a.id, username="alice", roles=["employee"], permissions=set())
    assert authz.can_read_document(identity, doc_b).allowed is False


def test_same_tenant_everyone_acl_allows(db):
    session, t_a, _t_b, u_a, _doc_b, _doc_b2 = db
    doc_a = Document(
        tenant_id=t_a.id, title="Memo A", document_type="text", classification="public",
        filename="memo.txt", mime_type="txt", size_bytes=1,
        storage_path="/tmp/memo.txt", created_by=u_a.id,
    )
    session.add(doc_a)
    session.flush()
    session.add(DocumentPermission(document_id=doc_a.id, action="read", principal_type="everyone", principal_id=None))
    session.commit()
    authz = AuthorizationService(session)
    identity = Identity(user_id=u_a.id, tenant_id=t_a.id, username="alice", roles=["employee"], permissions=set())
    allowed = authz.authorized_document_ids(identity)
    assert doc_a.id in allowed
