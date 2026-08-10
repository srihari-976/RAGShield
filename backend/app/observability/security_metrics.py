"""Security-event counters: ACL denials, cross-tenant attempts, policy
violations — queryable from the observability dashboard."""

import datetime

from sqlalchemy.orm import Session

from app.models.observability import AuditLog

SECURITY_ACTIONS = {
    "acl_denial": "chat query where evidence was blocked by ACL",
    "cross_tenant_attempt": "attempt to access a resource in another tenant",
    "policy_violation": "ABAC policy denied an action",
    "auth_failure": "failed login attempt",
}


def security_events(db: Session, tenant_id: str, hours: int = 24) -> list[dict]:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.tenant_id == tenant_id,
            AuditLog.created_at >= since,
            AuditLog.action.in_(list(SECURITY_ACTIONS.keys())),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": r.id,
            "action": r.action,
            "user_id": r.user_id,
            "query_text": r.query_text,
            "reason": r.reason,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


def security_counts(db: Session, tenant_id: str, hours: int = 24) -> dict[str, int]:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    counts: dict[str, int] = {}
    for action in SECURITY_ACTIONS:
        counts[action] = (
            db.query(AuditLog)
            .filter(AuditLog.tenant_id == tenant_id, AuditLog.created_at >= since, AuditLog.action == action)
            .count()
        )
    return counts
