"""Audit logging. Every sensitive action (chat query, document ops, ACL
changes, auth failures) is recorded. The audit log itself is protected by the
audit.view permission."""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.observability import AuditLog


def log_action(
    db: Session,
    tenant_id: str,
    action: str,
    user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    query_text: str | None = None,
    decision: str = "allowed",
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            query_text=query_text,
            decision=decision,
            reason=reason,
            metadata_json=json.dumps(metadata or {}),
            ip_address=ip_address,
        )
    )
    db.commit()
