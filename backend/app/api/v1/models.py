"""Model management: proxy Ollama /api/tags, validate model selection,
manage default chat/embedding models."""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.dependencies import get_authz_service, get_current_user
from app.auth.rbac import Identity
from app.core.config import get_settings
from app.core.database import get_db
from app.models.versioning import ModelConfig
from app.schemas.schemas import ModelConfigUpdate

router = APIRouter(tags=["models"])
settings = get_settings()


def fetch_installed_models() -> list[str]:
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{settings.ollama_base_url}/api/tags")
        if resp.status_code == 200:
            return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pass
    return []


@router.get("/models")
def list_models(identity: Identity = Depends(get_current_user), db: Session = Depends(get_db)):
    installed = fetch_installed_models()
    default_chat = (
        db.query(ModelConfig).filter(ModelConfig.kind == "chat", ModelConfig.is_default.is_(True)).first()
    )
    default_embed = (
        db.query(ModelConfig).filter(ModelConfig.kind == "embedding", ModelConfig.is_default.is_(True)).first()
    )
    return {
        "installed": installed,
        "default_chat": default_chat.model if default_chat else settings.chat_model,
        "default_embedding": default_embed.model if default_embed else settings.embedding_model,
        "reachable": bool(installed),
    }


@router.get("/admin/models/config")
def get_model_config(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    if not authz.is_admin(identity):
        raise HTTPException(status_code=403, detail="admin access required")
    configs = db.query(ModelConfig).all()
    return [
        {"id": c.id, "kind": c.kind, "model": c.model, "is_default": c.is_default, "enabled": c.enabled}
        for c in configs
    ]


@router.post("/admin/models/config")
def update_model_config(
    body: ModelConfigUpdate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    if not authz.is_admin(identity):
        raise HTTPException(status_code=403, detail="admin access required")
    installed = fetch_installed_models()
    changes: list[ModelConfig] = []
    for kind in ("chat", "embedding"):
        model = getattr(body, f"{kind}_model")
        if not model:
            continue
        if model not in installed:
            raise HTTPException(status_code=400, detail=f"model {model} is not installed on Ollama")
        cfg = db.query(ModelConfig).filter(ModelConfig.kind == kind).first()
        if cfg:
            cfg.model = model
        else:
            cfg = ModelConfig(kind=kind, model=model, is_default=True)
            db.add(cfg)
        changes.append(cfg)
    db.commit()
    return {"updated": [{"kind": c.kind, "model": c.model} for c in changes]}
