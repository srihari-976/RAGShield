from fastapi import APIRouter

from app.api.v1 import (
    admin_documents,
    admin_permissions,
    admin_tenants,
    admin_users,
    audit,
    auth,
    chat,
    evaluation,
    health,
    models,
    observability,
    settings,
    users,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(admin_users.router)
api_router.include_router(admin_tenants.router)
api_router.include_router(admin_documents.router)
api_router.include_router(admin_permissions.router)
api_router.include_router(models.router)
api_router.include_router(chat.router)
api_router.include_router(evaluation.router)
api_router.include_router(observability.router)
api_router.include_router(audit.router)
api_router.include_router(settings.router)
api_router.include_router(users.router)
