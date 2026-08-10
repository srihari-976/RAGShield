from fastapi import APIRouter, Depends

from app.core.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@router.get("/health/ready")
def readiness():
    import httpx

    checks = {"database": False, "qdrant": False, "ollama": False}
    try:
        from sqlalchemy import text

        from app.core.database import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass
    try:
        checks["qdrant"] = httpx.get(f"{settings.qdrant_url}/healthz", timeout=3).status_code == 200
    except Exception:
        pass
    try:
        checks["ollama"] = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3).status_code == 200
    except Exception:
        pass
    return {"ready": all(checks.values()), "checks": checks}
