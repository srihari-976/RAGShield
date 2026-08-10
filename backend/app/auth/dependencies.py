from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.rbac import Identity
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Identity:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="inactive or unknown user")
    authz = AuthorizationService(db)
    identity = authz.load_identity(user.id)
    if identity.tenant_id != payload.get("tenant_id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="tenant mismatch")
    return identity


def get_authz_service(db: Session = Depends(get_db)) -> AuthorizationService:
    return AuthorizationService(db)


def require_permission(permission: str):
    def checker(
        identity: Identity = Depends(get_current_user),
        authz: AuthorizationService = Depends(get_authz_service),
    ) -> Identity:
        decision = authz.can(identity, permission)
        if not decision:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=decision.reason)
        return identity

    return checker


def require_admin(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
) -> Identity:
    if not authz.is_admin(identity):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
    return identity


def get_request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID", "")


__all__ = [
    "get_current_user",
    "get_authz_service",
    "require_permission",
    "require_admin",
    "get_request_id",
]
