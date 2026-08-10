"""Audit log API — protected by audit.view permission."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.dependencies import get_authz_service, get_current_user
from app.auth.rbac import Identity
from app.core.database import get_db
from app.models.observability import AuditLog

router = APIRouter(prefix="/admin/audit", tags=["audit"])


@router.get("/logs", response_model=list[dict])
def audit_logs(
    limit: int = 100,
    action: str | None = None,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    if not authz.can(identity, "audit.view").allowed:
        raise HTTPException(status_code=403, detail="audit.view required")
    q = db.query(AuditLog).filter(AuditLog.tenant_id == identity.tenant_id)
    if action:
        q = q.filter(AuditLog.action == action)
    rows = q.order_by(AuditLog.created_at.desc()).limit(min(limit, 500)).all()
    return [
        {
            "id": r.id, "user_id": r.user_id, "action": r.action,
            "resource_type": r.resource_type, "resource_id": r.resource_id,
            "query_text": r.query_text, "decision": r.decision, "reason": r.reason,
            "metadata": json.loads(r.metadata_json or "{}"),
            "ip_address": r.ip_address, "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/security-events", response_model=list[dict])
def security_events(
    limit: int = 100,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    if not authz.can(identity, "audit.view").allowed:
        raise HTTPException(status_code=403, detail="audit.view required")
    from app.observability.security_metrics import SECURITY_ACTIONS

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.tenant_id == identity.tenant_id, AuditLog.action.in_(list(SECURITY_ACTIONS.keys())))
        .order_by(AuditLog.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [
        {
            "id": r.id, "action": r.action, "user_id": r.user_id,
            "query_text": r.query_text, "decision": r.decision, "reason": r.reason,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
