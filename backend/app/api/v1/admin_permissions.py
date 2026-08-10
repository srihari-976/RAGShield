"""Permission management: document ACLs + ABAC resource policies."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.dependencies import get_authz_service, get_current_user
from app.auth.policies import evaluate_policy
from app.auth.rbac import Identity
from app.core.database import get_db
from app.models.document import Document, DocumentPermission, ResourcePolicy
from app.observability.audit import log_action
from app.schemas.schemas import (
    DocumentPermissionCreate,
    DocumentPermissionSummary,
    PolicyCreate,
    PolicySummary,
)

router = APIRouter(prefix="/admin/permissions", tags=["admin-permissions"])


def _admin_or_raise(identity: Identity, authz: AuthorizationService) -> None:
    if not authz.is_admin(identity):
        raise HTTPException(status_code=403, detail="admin access required")


def _perm_or_raise(authz: AuthorizationService, identity: Identity, perm: str) -> None:
    if not authz.is_admin(identity) and not authz.can(identity, perm).allowed:
        raise HTTPException(status_code=403, detail=f"{perm} required")


@router.get("/documents/{document_id}", response_model=list[DocumentPermissionSummary])
def list_document_permissions(
    document_id: str,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _perm_or_raise(authz, identity, "permission.manage")
    doc = db.query(Document).filter(Document.id == document_id, Document.tenant_id == identity.tenant_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    perms = db.query(DocumentPermission).filter(DocumentPermission.document_id == document_id).all()
    return [
        DocumentPermissionSummary(
            id=p.id, document_id=p.document_id, action=p.action, principal_type=p.principal_type, principal_id=p.principal_id
        )
        for p in perms
    ]


@router.post("/documents/{document_id}", response_model=DocumentPermissionSummary, status_code=201)
def grant_document_permission(
    document_id: str,
    body: DocumentPermissionCreate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _perm_or_raise(authz, identity, "permission.manage")
    doc = db.query(Document).filter(Document.id == document_id, Document.tenant_id == identity.tenant_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="document not found")
    if body.principal_type not in ("user", "role", "everyone"):
        raise HTTPException(status_code=400, detail="principal_type must be user, role or everyone")
    existing = (
        db.query(DocumentPermission)
        .filter(
            DocumentPermission.document_id == document_id,
            DocumentPermission.action == body.action,
            DocumentPermission.principal_type == body.principal_type,
            DocumentPermission.principal_id == body.principal_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="permission already exists")
    perm = DocumentPermission(
        document_id=document_id,
        action=body.action,
        principal_type=body.principal_type,
        principal_id=body.principal_id,
    )
    db.add(perm)
    db.commit()
    db.refresh(perm)
    log_action(db, identity.tenant_id, "permission.grant", user_id=identity.user_id, resource_type="document", resource_id=document_id,
               metadata={"principal": f"{body.principal_type}:{body.principal_id}"})
    return DocumentPermissionSummary(
        id=perm.id, document_id=perm.document_id, action=perm.action, principal_type=perm.principal_type, principal_id=perm.principal_id
    )


@router.delete("/documents/{document_id}/{permission_id}", status_code=204)
def revoke_document_permission(
    document_id: str,
    permission_id: str,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _perm_or_raise(authz, identity, "permission.manage")
    perm = (
        db.query(DocumentPermission)
        .filter(DocumentPermission.id == permission_id, DocumentPermission.document_id == document_id)
        .first()
    )
    if not perm:
        raise HTTPException(status_code=404, detail="permission not found")
    db.delete(perm)
    db.commit()
    log_action(db, identity.tenant_id, "permission.revoke", user_id=identity.user_id, resource_type="document", resource_id=document_id)


@router.get("/policies", response_model=list[PolicySummary])
def list_policies(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _perm_or_raise(authz, identity, "permission.manage")
    policies = db.query(ResourcePolicy).filter(ResourcePolicy.tenant_id == identity.tenant_id).order_by(ResourcePolicy.priority).all()
    return [
        PolicySummary(
            id=p.id, tenant_id=p.tenant_id, name=p.name, description=p.description, action=p.action,
            rule=p.rule, effect=p.effect, priority=p.priority, is_active=p.is_active,
        )
        for p in policies
    ]


@router.post("/policies", response_model=PolicySummary, status_code=201)
def create_policy(
    body: PolicyCreate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _perm_or_raise(authz, identity, "permission.manage")
    try:
        json.loads(body.rule)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"rule must be valid JSON: {e}") from e
    policy = ResourcePolicy(
        tenant_id=identity.tenant_id,
        name=body.name,
        description=body.description,
        action=body.action,
        rule=body.rule,
        effect=body.effect,
        priority=body.priority,
        is_active=body.is_active,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    log_action(db, identity.tenant_id, "policy.create", user_id=identity.user_id, resource_type="policy", resource_id=policy.id)
    return PolicySummary(
        id=policy.id, tenant_id=policy.tenant_id, name=policy.name, description=policy.description, action=policy.action,
        rule=policy.rule, effect=policy.effect, priority=policy.priority, is_active=policy.is_active,
    )


@router.delete("/policies/{policy_id}", status_code=204)
def delete_policy(
    policy_id: str,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _perm_or_raise(authz, identity, "permission.manage")
    policy = db.query(ResourcePolicy).filter(ResourcePolicy.id == policy_id, ResourcePolicy.tenant_id == identity.tenant_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="policy not found")
    db.delete(policy)
    db.commit()
    log_action(db, identity.tenant_id, "policy.delete", user_id=identity.user_id, resource_type="policy", resource_id=policy_id)


@router.post("/policies/{policy_id}/test")
def test_policy(
    policy_id: str,
    subject: dict,
    resource: dict,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _perm_or_raise(authz, identity, "permission.manage")
    policy = db.query(ResourcePolicy).filter(ResourcePolicy.id == policy_id, ResourcePolicy.tenant_id == identity.tenant_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="policy not found")
    result = evaluate_policy(policy, subject, resource)
    return {"matches": result, "effect": policy.effect, "decision": result == (policy.effect == "allow")}
