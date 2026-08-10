"""Observability: latency percentiles, per-stage traces, security events."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.dependencies import get_authz_service, get_current_user
from app.auth.rbac import Identity
from app.core.database import get_db
from app.models.observability import TraceSpan
from app.observability.security_metrics import SECURITY_ACTIONS, security_counts, security_events
from app.observability.tracing import latency_percentiles

router = APIRouter(prefix="/admin/observability", tags=["observability"])


def _admin_or_raise(identity: Identity, authz: AuthorizationService) -> None:
    if not authz.is_admin(identity):
        raise HTTPException(status_code=403, detail="admin access required")


@router.get("/latency")
def latency(
    hours: int = 24,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    return {"chat_total": latency_percentiles(db, identity.tenant_id, hours)}


@router.get("/traces")
def traces(
    limit: int = 100,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    rows = (
        db.query(TraceSpan)
        .filter(TraceSpan.tenant_id == identity.tenant_id)
        .order_by(TraceSpan.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [
        {
            "id": t.id, "request_id": t.request_id, "span_name": t.span_name,
            "duration_ms": t.duration_ms, "status": t.status,
            "metadata": json.loads(t.metadata_json or "{}"),
            "created_at": t.created_at.isoformat(),
        }
        for t in rows
    ]


@router.get("/security")
def security(
    hours: int = 24,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    return {
        "actions": SECURITY_ACTIONS,
        "counts": security_counts(db, identity.tenant_id, hours),
        "events": security_events(db, identity.tenant_id, hours),
    }
