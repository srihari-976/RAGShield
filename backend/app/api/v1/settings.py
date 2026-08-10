"""Settings: prompt versions, experiments (canary), evaluation gate check."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.dependencies import get_authz_service, get_current_user
from app.auth.rbac import Identity
from app.core.config import get_settings
from app.core.database import get_db
from app.models.evaluation import EvaluationRun
from app.models.versioning import Experiment, PromptVersion
from app.schemas.schemas import ExperimentCreate, PromptVersionCreate

router = APIRouter(prefix="/admin/settings", tags=["settings"])
settings = get_settings()


def _admin_or_raise(identity: Identity, authz: AuthorizationService) -> None:
    if not authz.is_admin(identity):
        raise HTTPException(status_code=403, detail="admin access required")


# ---------------- Prompt versions ----------------

@router.get("/prompts", response_model=list[dict])
def list_prompts(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    rows = db.query(PromptVersion).order_by(PromptVersion.created_at.desc()).all()
    return [{"id": r.id, "version": r.version, "system_prompt": r.system_prompt, "is_active": r.is_active, "created_at": r.created_at.isoformat()} for r in rows]


@router.post("/prompts", status_code=201)
def create_prompt(
    body: PromptVersionCreate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    if db.query(PromptVersion).filter(PromptVersion.version == body.version).first():
        raise HTTPException(status_code=409, detail="version already exists")
    db.query(PromptVersion).update({"is_active": False})
    row = PromptVersion(
        version=body.version, system_prompt=body.system_prompt,
        grounding_prompt=body.grounding_prompt, is_active=True, created_by=identity.user_id,
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "version": row.version, "is_active": True}


@router.post("/prompts/{version}/activate")
def activate_prompt(
    version: str,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    row = db.query(PromptVersion).filter(PromptVersion.version == version).first()
    if not row:
        raise HTTPException(status_code=404, detail="prompt version not found")
    db.query(PromptVersion).update({"is_active": False})
    row.is_active = True
    db.commit()
    return {"activated": version}


# ---------------- Experiments (canary) ----------------

@router.get("/experiments", response_model=list[dict])
def list_experiments(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    rows = db.query(Experiment).all()
    return [{"id": r.id, "name": r.name, "rag_version_a": r.rag_version_a, "rag_version_b": r.rag_version_b, "traffic_percent_b": r.traffic_percent_b, "is_active": r.is_active} for r in rows]


@router.post("/experiments", status_code=201)
def create_experiment(
    body: ExperimentCreate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    row = Experiment(name=body.name, rag_version_a=body.rag_version_a, rag_version_b=body.rag_version_b, traffic_percent_b=body.traffic_percent_b)
    db.add(row)
    db.commit()
    return {"id": row.id}


@router.post("/experiments/{experiment_id}/toggle")
def toggle_experiment(
    experiment_id: str,
    active: bool,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    row = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="experiment not found")
    row.is_active = active
    db.commit()
    return {"id": row.id, "is_active": row.is_active}


# ---------------- Evaluation gate ----------------

@router.get("/evaluation-gate")
def evaluation_gate(
    run_id: str,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    """Gate check: Recall@5>=0.90, Precision@5>=0.80, Groundedness>=0.90,
    Completeness>=0.85, P95<5s, ACL violations=0."""
    _admin_or_raise(identity, authz)
    run = db.query(EvaluationRun).filter(EvaluationRun.id == run_id, EvaluationRun.tenant_id == identity.tenant_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    metrics = json.loads(run.metrics or "{}")
    checks = {
        "recall_at_5 >= 0.90": metrics.get("recall_at_5", 0) >= settings.evaluation_gate_recall_at_5,
        "precision_at_5 >= 0.80": metrics.get("precision_at_5", 0) >= settings.evaluation_gate_precision_at_5,
        "groundedness >= 0.90": metrics.get("groundedness", 0) >= settings.evaluation_gate_groundedness,
        "completeness >= 0.85": metrics.get("completeness", 0) >= settings.evaluation_gate_completeness,
        "p95 latency < 5s": (metrics.get("p95_latency_ms") or 99999) < settings.evaluation_gate_p95_seconds * 1000,
        "items > 0": metrics.get("items", 0) > 0,
    }
    passed = all(checks.values())
    return {"run_id": run_id, "metrics": metrics, "checks": checks, "passed": passed}
