"""First-run bootstrap: default tenant, system roles/permissions, admin user.
Idempotent."""

import logging

from sqlalchemy.orm import Session

from app.auth.rbac_seed import ensure_system_roles_and_permissions
from app.core.config import get_settings
from app.core.security import hash_password
from app.models.rbac import Role
from app.models.tenant import Tenant
from app.models.user import User
from app.models.versioning import ModelConfig, PromptVersion
from app.generation.prompts import DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
settings = get_settings()


def bootstrap(db: Session) -> None:
    ensure_system_roles_and_permissions(db)

    tenant = db.query(Tenant).filter(Tenant.name == settings.bootstrap_tenant_name).first()
    if not tenant:
        tenant = Tenant(name=settings.bootstrap_tenant_name, description="Default tenant")
        db.add(tenant)
        db.flush()
        logger.info("created tenant %s", tenant.id)

    admin = db.query(User).filter(User.username == settings.bootstrap_admin_username).first()
    if not admin:
        admin = User(
            tenant_id=tenant.id,
            username=settings.bootstrap_admin_username,
            email=settings.bootstrap_admin_email,
            password_hash=hash_password(settings.bootstrap_admin_password),
            full_name="Platform Administrator",
        )
        owner_role = db.query(Role).filter(Role.name == "owner").first()
        if owner_role:
            admin.roles = [owner_role]
        db.add(admin)
        db.flush()
        logger.info("created admin user %s", admin.username)

    if not db.query(PromptVersion).filter(PromptVersion.version == "v1").first():
        db.add(
            PromptVersion(
                version="v1",
                system_prompt=DEFAULT_SYSTEM_PROMPT,
                grounding_prompt=None,
                is_active=True,
                created_by=admin.id,
            )
        )
    if not db.query(ModelConfig).filter(ModelConfig.kind == "chat").first():
        db.add(ModelConfig(kind="chat", model=settings.chat_model, is_default=True))
    if not db.query(ModelConfig).filter(ModelConfig.kind == "embedding").first():
        db.add(ModelConfig(kind="embedding", model=settings.embedding_model, is_default=True))
    db.commit()
