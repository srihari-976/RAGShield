import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.document import ResourcePolicy
from app.models.rbac import Permission, Role


def ensure_system_roles_and_permissions(db: Session) -> dict[str, set[str]]:
    """Seed permission catalog and system roles. Returns role_name -> permission set."""
    from app.auth.rbac import PERMISSIONS, SYSTEM_ROLES

    perm_by_name: dict[str, Permission] = {}
    for name, desc in PERMISSIONS.items():
        p = db.query(Permission).filter(Permission.name == name).first()
        if not p:
            p = Permission(name=name, description=desc)
            db.add(p)
            db.flush()
        perm_by_name[name] = p

    role_map: dict[str, set[str]] = {}
    for role_name, spec in SYSTEM_ROLES.items():
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            role = Role(name=role_name, description=spec["description"], is_system=True)
            db.add(role)
            db.flush()
        role.permissions = [perm_by_name[n] for n in spec["permissions"]]
        role_map[role_name] = set(spec["permissions"])
    db.flush()
    return role_map


def load_role_permission_map(db: Session) -> dict[str, set[str]]:
    roles = db.query(Role).all()
    return {r.name: {p.name for p in r.permissions} for r in roles}
