from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.dependencies import get_authz_service, get_current_user
from app.auth.rbac import Identity
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.observability.audit import log_action
from app.schemas.schemas import RefreshRequest, TokenResponse, UserSummary

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


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


def _issue_tokens(db: Session, user: User) -> TokenResponse:
    roles = [r.name for r in user.roles]
    access = create_access_token(user.id, user.tenant_id, roles)
    refresh = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_password(refresh),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    db.commit()
    return TokenResponse(access_token=access, refresh_token=refresh, user=_user_summary(user))


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        log_action(db, user.tenant_id if user else "system", "auth_failure", query_text=form.username, decision="denied", reason="bad credentials")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="incorrect username or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user disabled")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    log_action(db, user.tenant_id, "login", user_id=user.id)
    return _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return _issue_tokens(db, user)


@router.get("/me", response_model=UserSummary)
def me(identity: Identity = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == identity.user_id).first()
    return _user_summary(user)


@router.get("/identity")
def identity_info(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
):
    """Exposes the resolved identity (roles + effective permissions + tenant)
    so the UI can render role-aware sections."""
    return {
        "user_id": identity.user_id,
        "tenant_id": identity.tenant_id,
        "username": identity.username,
        "full_name": identity.full_name,
        "roles": identity.roles,
        "permissions": sorted(identity.permissions),
        "is_admin": authz.is_admin(identity),
    }
