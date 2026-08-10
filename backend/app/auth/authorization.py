"""Authorization service: RBAC + ACL + ABAC, single decision point.

Every access decision in the platform (API routes AND retrieval) goes through
`can` or `can_read_document`. The retriever only receives a filter built from
these decisions, so the LLM never sees unauthorized evidence.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.auth.policies import evaluate_policies
from app.auth.rbac import Identity
from app.models.document import Document, DocumentPermission
from app.models.rbac import Permission, Role

ADMIN_ROLES = {"owner", "admin"}
EVERYONE = "everyone"


@dataclass
class Decision:
    allowed: bool
    reason: str = ""
    via: str = ""  # rbac | acl | abac | admin

    def __bool__(self) -> bool:
        return self.allowed


class AuthorizationService:
    def __init__(self, db: Session):
        self.db = db

    def load_identity(self, user_id: str) -> Identity:
        from app.models.user import User

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("user not found")
        role_names = [r.name for r in user.roles]
        role_map = self._role_permission_map()
        perms: set[str] = set()
        for r in role_names:
            perms |= role_map.get(r, set())
        return Identity(
            user_id=user.id,
            tenant_id=user.tenant_id,
            username=user.username,
            roles=role_names,
            permissions=perms,
            department=user.department,
            email=user.email,
            full_name=user.full_name,
        )

    def _role_permission_map(self) -> dict[str, set[str]]:
        roles = self.db.query(Role).all()
        return {r.name: {p.name for p in r.permissions} for r in roles}

    def has_permission(self, identity: Identity, permission: str) -> bool:
        return permission in identity.permissions

    def can(self, identity: Identity, permission: str) -> Decision:
        if self.has_permission(identity, permission):
            return Decision(True, via="rbac")
        return Decision(False, f"missing permission {permission}", via="rbac")

    def is_admin(self, identity: Identity) -> bool:
        return bool(set(identity.roles) & ADMIN_ROLES)

    def can_read_document(self, identity: Identity, document: Document) -> Decision:
        """RBAC-adjacent admin override + tenant + ACL + ABAC."""
        if identity.tenant_id != document.tenant_id:
            return Decision(False, "cross-tenant access denied", via="tenant")
        if set(identity.roles) & ADMIN_ROLES:
            return Decision(True, via="admin")
        if identity.user_id == document.owner_id:
            return Decision(True, via="acl")

        acl_ok = self._check_acl(identity, document, "read")
        if acl_ok.allowed:
            return acl_ok

        abac_ok = self._check_abac(identity, document, "read")
        if abac_ok.allowed:
            return abac_ok
        return Decision(False, "not authorized to read this document", via="acl")

    def _check_acl(self, identity: Identity, document: Document, action: str) -> Decision:
        perms = (
            self.db.query(DocumentPermission)
            .filter(
                DocumentPermission.document_id == document.id,
                DocumentPermission.action == action,
            )
            .all()
        )
        for p in perms:
            if p.principal_type == EVERYONE:
                return Decision(True, via="acl")
            if p.principal_type == "user" and p.principal_id == identity.user_id:
                return Decision(True, via="acl")
            if p.principal_type == "role" and p.principal_id in identity.roles:
                return Decision(True, via="acl")
        return Decision(False, via="acl")

    def _check_abac(self, identity: Identity, document: Document, action: str) -> Decision:
        subject_attrs = {
            "id": identity.user_id,
            "tenant_id": identity.tenant_id,
            "roles": identity.roles,
            "department": identity.department or "",
            "email": identity.email or "",
        }
        resource_attrs = {
            "id": document.id,
            "tenant_id": document.tenant_id,
            "owner_id": document.owner_id or "",
            "classification": document.classification,
            "document_type": document.document_type,
        }
        if evaluate_policies(self.db, identity.tenant_id, action, subject_attrs, resource_attrs):
            return Decision(True, via="abac")
        return Decision(False, via="abac")

    def authorized_document_ids(self, identity: Identity) -> set[str]:
        """All document ids readable by this identity (used for retrieval filtering)."""
        from sqlalchemy import or_

        if self.is_admin(identity):
            ids = [d.id for d in self.db.query(Document.id).filter(Document.tenant_id == identity.tenant_id).all()]
            return set(ids)

        own = self.db.query(Document.id).filter(
            Document.tenant_id == identity.tenant_id, Document.owner_id == identity.user_id
        ).all()

        everyone_ids = self.db.query(DocumentPermission.document_id).filter(
            DocumentPermission.action == "read",
            DocumentPermission.principal_type == EVERYONE,
        ).all()

        user_ids = self.db.query(DocumentPermission.document_id).filter(
            DocumentPermission.action == "read",
            DocumentPermission.principal_type == "user",
            DocumentPermission.principal_id == identity.user_id,
        ).all()

        role_ids = self.db.query(DocumentPermission.document_id).filter(
            DocumentPermission.action == "read",
            DocumentPermission.principal_type == "role",
            DocumentPermission.principal_id.in_(identity.roles),
        ).all()

        doc_ids = {r[0] for r in own} | {r[0] for r in everyone_ids} | {r[0] for r in user_ids} | {r[0] for r in role_ids}

        # ABAC: evaluate policies per candidate document (cheap at this scale)
        if doc_ids:
            candidates = self.db.query(Document).filter(
                Document.tenant_id == identity.tenant_id, Document.id.in_(doc_ids)
            ).all()
        else:
            candidates = self.db.query(Document).filter(Document.tenant_id == identity.tenant_id).all()
        abac_ok = set()
        subject_attrs = {
            "id": identity.user_id,
            "tenant_id": identity.tenant_id,
            "roles": identity.roles,
            "department": identity.department or "",
            "email": identity.email or "",
        }
        for d in candidates:
            resource_attrs = {
                "id": d.id,
                "tenant_id": d.tenant_id,
                "owner_id": d.owner_id or "",
                "classification": d.classification,
                "document_type": d.document_type,
            }
            if evaluate_policies(self.db, identity.tenant_id, "read", subject_attrs, resource_attrs):
                abac_ok.add(d.id)

        return doc_ids | abac_ok
