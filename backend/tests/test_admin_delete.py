"""Unit tests for destructive-admin helpers: tenant cascade delete and user
grant revocation. `_cascade_delete_tenant` must remove every row referencing the
tenant (FK-safe order) while leaving sibling tenants untouched; the user helper
must revoke only that user's personal document grants."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api.v1.admin_tenants import _cascade_delete_tenant
from app.api.v1.admin_users import _revoke_user_grants
from app.core.database import Base
from app.core.security import hash_password
from app.models.chat import Conversation, Message
from app.models.document import Document, DocumentPermission, DocumentVersion, ResourcePolicy
from app.models.evaluation import Adjudication, EvaluationItem, EvaluationRun, GoldenQuestion, Rater, Rating
from app.models.observability import AuditLog, TraceSpan
from app.models.rbac import Role
from app.models.tenant import Tenant
from app.models.user import RefreshToken, User


def _mk_tenant(session: Session, name: str, with_data: bool) -> Tenant:
    tenant = Tenant(name=name, description="")
    session.add(tenant)
    session.flush()
    if not with_data:
        return tenant
    owner = Role(name=f"owner_{name}", description="", is_system=True)
    session.add(owner)
    session.flush()
    user = User(tenant_id=tenant.id, username=f"u_{name}", email=f"u_{name}@t.co",
                password_hash=hash_password("password123"), roles=[owner])
    session.add(user)
    session.flush()

    doc = Document(tenant_id=tenant.id, title=f"doc {name}", document_type="text",
                   classification="restricted", filename=f"{name}.txt", mime_type="txt",
                   size_bytes=1, storage_path=f"/tmp/{name}.txt", created_by=user.id, owner_id=user.id)
    session.add(doc)
    session.flush()
    session.add(DocumentPermission(document_id=doc.id, action="read", principal_type="user", principal_id=user.id))
    session.add(DocumentVersion(document_id=doc.id, version=1, storage_path=f"/tmp/{name}.v1.txt",
                                size_bytes=1, created_by=user.id))
    session.add(ResourcePolicy(tenant_id=tenant.id, name=f"policy {name}", rule="{}"))

    conv = Conversation(tenant_id=tenant.id, user_id=user.id, title=f"conv {name}")
    session.add(conv)
    session.flush()
    session.add(Message(conversation_id=conv.id, role="user", content="hi"))

    session.add(GoldenQuestion(tenant_id=tenant.id, question=f"q {name}", expected_document_ids="[]"))
    run = EvaluationRun(tenant_id=tenant.id, name=f"run {name}", created_by=user.id)
    session.add(run)
    session.flush()
    item = EvaluationItem(run_id=run.id, question=f"qi {name}")
    session.add(item)
    session.flush()
    rater = Rater(user_id=user.id, display_name=name)
    session.add(rater)
    session.flush()
    session.add(Rating(item_id=item.id, rater_id=rater.id, rubric_version="v1"))
    session.add(Adjudication(item_id=item.id, dimension="relevance", adjudicator_id=rater.id,
                             original_scores="{}", final_score=4))
    session.add(RefreshToken(user_id=user.id, token_hash="abc", expires_at=__import__("datetime").datetime.now()))
    session.add(AuditLog(tenant_id=tenant.id, user_id=user.id, action="chat.query"))
    session.add(TraceSpan(tenant_id=tenant.id, user_id=user.id, request_id="r", span_name="x"))
    return tenant


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add_all([_mk_tenant(session, "TenantA", True), _mk_tenant(session, "TenantB", True)])
    session.commit()
    yield session
    session.close()


def _counts(db: Session) -> dict[str, int]:
    return {
        "tenants": db.query(Tenant).count(),
        "users": db.query(User).count(),
        "documents": db.query(Document).count(),
        "permissions": db.query(DocumentPermission).count(),
        "versions": db.query(DocumentVersion).count(),
        "policies": db.query(ResourcePolicy).count(),
        "conversations": db.query(Conversation).count(),
        "messages": db.query(Message).count(),
        "golden": db.query(GoldenQuestion).count(),
        "runs": db.query(EvaluationRun).count(),
        "items": db.query(EvaluationItem).count(),
        "raters": db.query(Rater).count(),
        "ratings": db.query(Rating).count(),
        "adjudications": db.query(Adjudication).count(),
        "refresh_tokens": db.query(RefreshToken).count(),
        "audit_logs": db.query(AuditLog).count(),
        "traces": db.query(TraceSpan).count(),
    }


def _seed_total(db: Session) -> dict[str, int]:
    return {
        "tenants": 2,
        "users": 2,
        "documents": 2,
        "permissions": 2,
        "versions": 2,
        "policies": 2,
        "conversations": 2,
        "messages": 2,
        "golden": 2,
        "runs": 2,
        "items": 2,
        "raters": 2,
        "ratings": 2,
        "adjudications": 2,
        "refresh_tokens": 2,
        "audit_logs": 2,
        "traces": 2,
    }


def test_cascade_delete_tenant_removes_everything_and_counts(db):
    session = db
    tenant_a = session.query(Tenant).filter(Tenant.name == "TenantA").first()
    assert tenant_a is not None
    counts = _cascade_delete_tenant(session, tenant_a.id)
    session.commit()

    assert counts == {"users": 1, "documents": 1}
    remaining = _counts(session)
    total = _seed_total(session)
    for key, expected in total.items():
        assert remaining[key] == expected // 2, f"{key}: {remaining[key]} left, expected {expected // 2}"


def test_sibling_tenant_survives(db):
    session = db
    tenant_b = session.query(Tenant).filter(Tenant.name == "TenantB").first()
    _cascade_delete_tenant(session, tenant_b.id)
    session.commit()
    tenant_a = session.query(Tenant).filter(Tenant.name == "TenantA").first()
    assert tenant_a is not None
    assert session.query(User).filter(User.tenant_id == tenant_a.id).count() == 1
    assert session.query(Document).filter(Document.tenant_id == tenant_a.id).count() == 1


def test_cascade_delete_tenant_unknown_is_noop(db):
    session = db
    before = _counts(session)
    _cascade_delete_tenant(session, "no-such-tenant")
    session.commit()
    assert _counts(session) == before


def test_revoke_user_grants_only_removes_that_user(db):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine)
    tenant = Tenant(name="T", description="")
    session.add(tenant)
    session.flush()
    u1 = User(tenant_id=tenant.id, username="a", email="a@t.co", password_hash=hash_password("password123"))
    u2 = User(tenant_id=tenant.id, username="b", email="b@t.co", password_hash=hash_password("password123"))
    session.add_all([u1, u2])
    session.flush()
    doc = Document(tenant_id=tenant.id, title="d", document_type="text", classification="restricted",
                   filename="d.txt", mime_type="txt", size_bytes=1, storage_path="/tmp/d.txt", created_by=u1.id)
    session.add(doc)
    session.flush()
    session.add_all([
        DocumentPermission(document_id=doc.id, action="read", principal_type="user", principal_id=u1.id),
        DocumentPermission(document_id=doc.id, action="read", principal_type="user", principal_id=u2.id),
        DocumentPermission(document_id=doc.id, action="read", principal_type="role", principal_id="employee"),
        DocumentPermission(document_id=doc.id, action="read", principal_type="everyone", principal_id=None),
    ])
    session.commit()

    _revoke_user_grants(session, u1.id)
    session.commit()

    remaining = session.query(DocumentPermission).filter(DocumentPermission.document_id == doc.id).all()
    assert {(p.principal_type, p.principal_id) for p in remaining} == {
        ("user", u2.id), ("role", "employee"), ("everyone", None),
    }
    session.close()