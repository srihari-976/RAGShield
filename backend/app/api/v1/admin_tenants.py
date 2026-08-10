"""Tenant workspace management: create isolated tenants (e.g. separate
lecturer / student workspaces), each with its own admin user. Only users
holding the tenant.manage permission can manage tenants."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.dependencies import get_authz_service, get_current_user
from app.auth.rbac import Identity
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import hash_password
from app.models.document import Document
from app.models.rbac import Role
from app.models.tenant import Tenant
from app.models.user import User
from app.observability.audit import log_action
from app.schemas.schemas import TenantCreate, TenantSummary, TenantUpdate

router = APIRouter(prefix="/admin/tenants", tags=["admin-tenants"])
settings = get_settings()


def _tenant_summary(db: Session, t: Tenant) -> TenantSummary:
    user_count = db.query(func.count(User.id)).filter(User.tenant_id == t.id).scalar() or 0
    doc_count = db.query(func.count(Document.id)).filter(Document.tenant_id == t.id).scalar() or 0
    return TenantSummary(
        id=t.id, name=t.name, description=t.description, is_active=t.is_active,
        created_at=t.created_at, user_count=user_count, document_count=doc_count,
    )


def _manage_or_raise(identity: Identity, authz: AuthorizationService) -> None:
    if not authz.can(identity, "tenant.manage").allowed:
        raise HTTPException(status_code=403, detail="tenant.manage required")


@router.get("", response_model=list[TenantSummary])
def list_tenants(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _manage_or_raise(identity, authz)
    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    return [_tenant_summary(db, t) for t in tenants]


@router.post("", response_model=TenantSummary, status_code=201)
def create_tenant(
    body: TenantCreate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    """Creates an isolated tenant workspace, optionally with its own admin user."""
    _manage_or_raise(identity, authz)
    if db.query(Tenant).filter(Tenant.name == body.name).first():
        raise HTTPException(status_code=409, detail="tenant name already exists")
    tenant = Tenant(name=body.name, description=body.description)
    db.add(tenant)
    db.flush()

    admin_user = None
    if body.admin_username and body.admin_password:
        if db.query(User).filter(User.username == body.admin_username).first():
            db.rollback()
            raise HTTPException(status_code=409, detail="admin username already exists")
        admin_user = User(
            tenant_id=tenant.id,
            username=body.admin_username,
            email=body.admin_email or f"{body.admin_username}@example.com",
            password_hash=hash_password(body.admin_password),
            full_name=f"{body.admin_username} (admin)",
        )
        owner_role = db.query(Role).filter(Role.name == "owner").first()
        if owner_role:
            admin_user.roles = [owner_role]
        db.add(admin_user)
        db.flush()

    db.commit()
    log_action(
        db, identity.tenant_id, "tenant.create", user_id=identity.user_id,
        resource_type="tenant", resource_id=tenant.id,
        metadata={"name": tenant.name, "admin_created": admin_user is not None},
    )
    return _tenant_summary(db, tenant)


@router.patch("/{tenant_id}", response_model=TenantSummary)
def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _manage_or_raise(identity, authz)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("name") and db.query(Tenant).filter(Tenant.name == data["name"], Tenant.id != tenant_id).first():
        raise HTTPException(status_code=409, detail="tenant name already exists")
    for k, v in data.items():
        setattr(tenant, k, v)
    db.commit()
    db.refresh(tenant)
    log_action(db, identity.tenant_id, "tenant.update", user_id=identity.user_id, resource_type="tenant", resource_id=tenant.id)
    return _tenant_summary(db, tenant)
