from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.dependencies import get_authz_service, get_current_user
from app.auth.rbac import Identity
from app.core.database import get_db
from app.models.rbac import Permission, Role
from app.schemas.schemas import RoleSummary, UserCreate, UserSummary, UserUpdate
from app.core.security import hash_password
from app.models.user import User
from app.observability.audit import log_action

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


def _user_summary(user: User) -> UserSummary:
    return UserSummary(
        id=user.id,
        tenant_id=user.tenant_id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        department=user.department,
        is_active=user.is_active,
        roles=[r.name for r in user.roles],
        created_at=user.created_at,
    )


@router.get("", response_model=list[UserSummary])
def list_users(
    tenant_id: str | None = None,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    if not authz.can(identity, "user.create").allowed and not authz.is_admin(identity) and not authz.can(identity, "permission.manage").allowed:
        raise HTTPException(status_code=403, detail="not authorized")
    q = db.query(User).filter(User.tenant_id == identity.tenant_id)
    if tenant_id:
        if tenant_id != identity.tenant_id and not authz.can(identity, "tenant.manage").allowed:
            raise HTTPException(status_code=403, detail="tenant.manage required for cross-tenant access")
        q = db.query(User).filter(User.tenant_id == tenant_id)
    users = q.order_by(User.created_at.desc()).all()
    return [_user_summary(u) for u in users]


@router.post("", response_model=UserSummary, status_code=201)
def create_user(
    body: UserCreate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    if not authz.can(identity, "user.create").allowed and not authz.is_admin(identity):
        raise HTTPException(status_code=403, detail="not authorized")
    tenant_id = getattr(body, "tenant_id", None) or identity.tenant_id
    if tenant_id != identity.tenant_id:
        if not authz.can(identity, "tenant.manage").allowed:
            raise HTTPException(status_code=403, detail="tenant.manage required for cross-tenant access")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=409, detail="username already exists")
    user = User(
        tenant_id=tenant_id,
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        department=body.department,
    )
    db.add(user)
    db.flush()
    if body.roles:
        roles = db.query(Role).filter(Role.name.in_(body.roles)).all()
        user.roles = roles
    db.commit()
    db.refresh(user)
    log_action(db, identity.tenant_id, "user.create", user_id=identity.user_id, resource_type="user", resource_id=user.id)
    return _user_summary(user)


@router.get("/{user_id}", response_model=UserSummary)
def get_user(
    user_id: str,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    if not authz.is_admin(identity) and user_id != identity.user_id:
        raise HTTPException(status_code=403, detail="not authorized")
    user = db.query(User).filter(User.id == user_id, User.tenant_id == identity.tenant_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return _user_summary(user)


@router.patch("/{user_id}", response_model=UserSummary)
def update_user(
    user_id: str,
    body: UserUpdate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    if not authz.can(identity, "user.edit").allowed and not authz.is_admin(identity):
        raise HTTPException(status_code=403, detail="not authorized")
    user = db.query(User).filter(User.id == user_id, User.tenant_id == identity.tenant_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    data = body.model_dump(exclude_unset=True)
    roles = data.pop("roles", None)
    password = data.pop("password", None)
    for k, v in data.items():
        setattr(user, k, v)
    if password:
        user.password_hash = hash_password(password)
    if roles is not None:
        user.roles = db.query(Role).filter(Role.name.in_(roles)).all()
    db.commit()
    db.refresh(user)
    log_action(db, identity.tenant_id, "user.edit", user_id=identity.user_id, resource_type="user", resource_id=user.id)
    return _user_summary(user)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: str,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    if not authz.can(identity, "user.delete").allowed and not authz.is_admin(identity):
        raise HTTPException(status_code=403, detail="not authorized")
    user = db.query(User).filter(User.id == user_id, User.tenant_id == identity.tenant_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    if user.id == identity.user_id:
        raise HTTPException(status_code=400, detail="cannot delete yourself")
    user.is_active = False
    db.commit()
    log_action(db, identity.tenant_id, "user.delete", user_id=identity.user_id, resource_type="user", resource_id=user.id)


@router.get("/roles/list", response_model=list[RoleSummary])
def list_roles(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    if not authz.is_admin(identity) and not authz.can(identity, "permission.manage").allowed:
        raise HTTPException(status_code=403, detail="admin access required")
    roles = db.query(Role).all()
    return [
        RoleSummary(id=r.id, name=r.name, description=r.description, is_system=r.is_system, permissions=[p.name for p in r.permissions])
        for r in roles
    ]


@router.get("/permissions/list", response_model=list[str])
def list_permissions(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    if not authz.is_admin(identity) and not authz.can(identity, "permission.manage").allowed:
        raise HTTPException(status_code=403, detail="admin access required")
    return [p.name for p in db.query(Permission).all()]
