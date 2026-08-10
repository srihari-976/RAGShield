"""Evaluation: golden questions, offline runs with Recall@K/Precision@K/MRR/
nDCG, LLM-judge quality metrics, human ratings, adjudication, Krippendorff."""

import json
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.dependencies import get_authz_service, get_current_user
from app.auth.rbac import Identity
from app.core.config import get_settings
from app.core.database import get_db
from app.evaluation.adjudication import adjudicate, flag_disagreements, rater_agreement
from app.evaluation.llm_judge import judge_answer
from app.evaluation.offline_metrics import compute_metrics
from app.generation.gateway import build_prompt, get_active_chat_model, get_active_prompt
from app.generation.grounding import verify_answer
from app.models.evaluation import (
    Adjudication,
    EvaluationItem,
    EvaluationRun,
    GoldenQuestion,
    Rater,
    Rating,
)
from app.schemas.schemas import (
    AdjudicationCreate,
    EvaluationRunCreate,
    GoldenQuestionCreate,
    RatingCreate,
)

router = APIRouter(tags=["evaluation"])
settings = get_settings()


def _admin_or_raise(identity: Identity, authz: AuthorizationService) -> None:
    if not authz.is_admin(identity):
        raise HTTPException(status_code=403, detail="admin access required")


def _generate_answer(db: Session, identity: Identity, question: str, chunks: list[dict], model: str | None) -> tuple[str, dict]:
    """Synchronous grounded completion for an evaluation run (no conversation persisted)."""
    prompt = get_active_prompt(db)
    model = model or get_active_chat_model(db)
    messages, _ = build_prompt(question, chunks, prompt, identity)
    with httpx.Client(timeout=settings.ollama_timeout) as client:
        resp = client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"num_ctx": 4096, "temperature": 0.2, "num_predict": 600},
            },
        )
    answer = resp.json().get("message", {}).get("content", "")
    chunk_texts = [{"chunk_id": c.get("chunk_id"), "document_id": c["payload"].get("document_id"), "chunk_text": c["payload"].get("text", "")} for c in chunks]
    return answer, verify_answer(answer, chunk_texts)


# ---------------- Golden questions ----------------

@router.get("/admin/evaluation/golden", response_model=list[dict])
def list_golden(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    rows = db.query(GoldenQuestion).filter(GoldenQuestion.tenant_id == identity.tenant_id).all()
    return [{"id": r.id, "question": r.question, "expected_document_ids": json.loads(r.expected_document_ids), "category": r.category} for r in rows]


@router.post("/admin/evaluation/golden", status_code=201)
def create_golden(
    body: GoldenQuestionCreate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    row = GoldenQuestion(
        tenant_id=identity.tenant_id,
        question=body.question,
        expected_document_ids=json.dumps(body.expected_document_ids),
        category=body.category,
    )
    db.add(row)
    db.commit()
    return {"id": row.id}


@router.delete("/admin/evaluation/golden/{question_id}", status_code=204)
def delete_golden(
    question_id: str,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    row = db.query(GoldenQuestion).filter(GoldenQuestion.id == question_id, GoldenQuestion.tenant_id == identity.tenant_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    db.delete(row)
    db.commit()


# ---------------- Offline runs ----------------

@router.post("/admin/evaluation/runs", status_code=201)
def create_evaluation_run(
    body: EvaluationRunCreate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    run = EvaluationRun(
        tenant_id=identity.tenant_id,
        name=body.name,
        rag_version=body.rag_version,
        prompt_version=body.prompt_version,
        retriever_config=json.dumps(body.retriever_config or {}),
        created_by=identity.user_id,
    )
    db.add(run)
    db.flush()

    from app.retrieval.service import RetrievalService

    questions = db.query(GoldenQuestion).filter(GoldenQuestion.tenant_id == identity.tenant_id).all()
    model = get_active_chat_model(db)
    aggregate = {
        "recall_at_5": [], "precision_at_5": [], "mrr": [], "ndcg": [],
        "groundedness": [], "completeness": [], "relevance": [],
        "latencies_ms": [],
    }
    for q in questions:
        expected = json.loads(q.expected_document_ids)
        retriever = RetrievalService(db, authz, identity)
        result = retriever.retrieve(q.question)
        retrieved_doc_ids = list(dict.fromkeys(c["payload"].get("document_id") for c in result["chunks"] if c["payload"].get("document_id")))
        metrics = compute_metrics(retrieved_doc_ids, expected, k=5)

        answer = ""
        grounding = {"mode": "none", "overall_grounded": True, "abstained": False}
        quality = {"groundedness": 0.0, "completeness": 0.0, "relevance": 0.0}
        if result["chunks"]:
            t_ans = time.perf_counter()
            answer, grounding = _generate_answer(db, identity, q.question, result["chunks"], model)
            quality = judge_answer(q.question, answer, [c["payload"].get("text", "") for c in result["chunks"]], model)
            item_latency = int((time.perf_counter() - t_ans) * 1000) + sum(result["timings"].values())
        else:
            item_latency = sum(result["timings"].values())

        item = EvaluationItem(
            run_id=run.id,
            question=q.question,
            answer=answer,
            expected_document_ids=json.dumps(expected),
            retrieved_document_ids=json.dumps(retrieved_doc_ids),
            recall_at_k=metrics["recall_at_5"],
            precision_at_k=metrics["precision_at_5"],
            mrr=metrics["mrr"],
            ndcg=metrics["ndcg"],
            groundedness=quality["groundedness"],
            completeness=quality["completeness"],
            relevance=quality["relevance"],
            latency_ms=item_latency,
        )
        db.add(item)
        db.flush()

        aggregate["recall_at_5"].append(metrics["recall_at_5"])
        aggregate["precision_at_5"].append(metrics["precision_at_5"])
        aggregate["mrr"].append(metrics["mrr"])
        aggregate["ndcg"].append(metrics["ndcg"])
        aggregate["groundedness"].append(quality["groundedness"])
        aggregate["completeness"].append(quality["completeness"])
        aggregate["relevance"].append(quality["relevance"])
        aggregate["latencies_ms"].append(item_latency or 0)

    import statistics

    def avg(vals):
        return round(statistics.mean(vals), 4) if vals else 0.0

    latencies = sorted(aggregate["latencies_ms"])
    run.metrics = json.dumps({
        "recall_at_5": avg(aggregate["recall_at_5"]),
        "precision_at_5": avg(aggregate["precision_at_5"]),
        "mrr": avg(aggregate["mrr"]),
        "ndcg": avg(aggregate["ndcg"]),
        "groundedness": avg(aggregate["groundedness"]),
        "completeness": avg(aggregate["completeness"]),
        "relevance": avg(aggregate["relevance"]),
        "p95_latency_ms": latencies[int(len(latencies) * 0.95)] if latencies else None,
        "items": len(questions),
    })
    run.status = "COMPLETED"
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"run_id": run.id, "metrics": json.loads(run.metrics)}


@router.get("/admin/evaluation/runs", response_model=list[dict])
def list_runs(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    runs = db.query(EvaluationRun).filter(EvaluationRun.tenant_id == identity.tenant_id).order_by(EvaluationRun.created_at.desc()).all()
    return [
        {
            "id": r.id, "name": r.name, "rag_version": r.rag_version, "prompt_version": r.prompt_version,
            "status": r.status, "metrics": json.loads(r.metrics) if r.metrics else None, "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]


@router.get("/admin/evaluation/runs/{run_id}/items", response_model=list[dict])
def run_items(
    run_id: str,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    run = db.query(EvaluationRun).filter(EvaluationRun.id == run_id, EvaluationRun.tenant_id == identity.tenant_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return [
        {
            "id": i.id, "question": i.question, "answer": i.answer,
            "retrieved_document_ids": json.loads(i.retrieved_document_ids) if i.retrieved_document_ids else [],
            "expected_document_ids": json.loads(i.expected_document_ids) if i.expected_document_ids else [],
            "recall_at_k": i.recall_at_k, "precision_at_k": i.precision_at_k, "mrr": i.mrr, "ndcg": i.ndcg,
            "groundedness": i.groundedness, "completeness": i.completeness, "relevance": i.relevance,
            "latency_ms": i.latency_ms,
        }
        for i in run.items
    ]


# ---------------- Human evaluation ----------------

@router.post("/evaluation/raters", status_code=201)
def register_rater(
    display_name: str,
    is_adjudicator: bool = False,
    identity: Identity = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rater = db.query(Rater).filter(Rater.user_id == identity.user_id).first()
    if rater:
        rater.display_name = display_name
        rater.is_adjudicator = is_adjudicator
        db.commit()
        return {"id": rater.id}
    rater = Rater(user_id=identity.user_id, display_name=display_name, is_adjudicator=is_adjudicator)
    db.add(rater)
    db.commit()
    return {"id": rater.id}


@router.get("/evaluation/items/for-rating", response_model=list[dict])
def items_for_rating(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    if not authz.can(identity, "evaluation.rate").allowed:
        raise HTTPException(status_code=403, detail="not authorized")
    items = (
        db.query(EvaluationItem)
        .join(EvaluationRun)
        .filter(EvaluationRun.tenant_id == identity.tenant_id)
        .limit(50)
        .all()
    )
    return [
        {"id": i.id, "question": i.question, "answer": i.answer,
         "retrieved_document_ids": json.loads(i.retrieved_document_ids) if i.retrieved_document_ids else []}
        for i in items
    ]


@router.post("/evaluation/ratings", status_code=201)
def submit_rating(
    body: RatingCreate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    if not authz.can(identity, "evaluation.rate").allowed:
        raise HTTPException(status_code=403, detail="not authorized")
    rater = db.query(Rater).filter(Rater.user_id == identity.user_id).first()
    if not rater:
        rater = Rater(user_id=identity.user_id, display_name=identity.username)
        db.add(rater)
        db.flush()
    rating = db.query(Rating).filter(Rating.item_id == body.item_id, Rating.rater_id == rater.id).first()
    if rating:
        rating.groundedness = body.groundedness
        rating.relevance = body.relevance
        rating.completeness = body.completeness
        rating.citation_quality = body.citation_quality
        rating.comment = body.comment
    else:
        rating = Rating(
            item_id=body.item_id, rater_id=rater.id,
            groundedness=body.groundedness, relevance=body.relevance,
            completeness=body.completeness, citation_quality=body.citation_quality,
            comment=body.comment,
        )
        db.add(rating)
    db.commit()
    return {"id": rating.id}


@router.get("/admin/evaluation/agreement")
def agreement(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    """Krippendorff's Alpha per dimension over human ratings."""
    _admin_or_raise(identity, authz)
    return {
        "dimensions": [
            rater_agreement(db, "groundedness"),
            rater_agreement(db, "relevance"),
            rater_agreement(db, "completeness"),
            rater_agreement(db, "citation_quality"),
        ]
    }


@router.get("/admin/evaluation/disagreements")
def disagreements(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    return {"disagreements": flag_disagreements(db)}


@router.post("/admin/evaluation/adjudicate", status_code=201)
def create_adjudication(
    body: AdjudicationCreate,
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    rater = db.query(Rater).filter(Rater.user_id == identity.user_id).first()
    if not rater:
        rater = Rater(user_id=identity.user_id, display_name=identity.username, is_adjudicator=True)
        db.add(rater)
        db.flush()
    record = adjudicate(db, body.item_id, body.dimension, rater.id, body.final_score, body.reason)
    return {"id": record.id, "final_score": record.final_score, "reason": record.reason}


@router.get("/admin/evaluation/adjudications", response_model=list[dict])
def list_adjudications(
    identity: Identity = Depends(get_current_user),
    authz: AuthorizationService = Depends(get_authz_service),
    db: Session = Depends(get_db),
):
    _admin_or_raise(identity, authz)
    rows = db.query(Adjudication).all()
    return [
        {"id": r.id, "item_id": r.item_id, "dimension": r.dimension, "final_score": r.final_score,
         "original_scores": json.loads(r.original_scores), "reason": r.reason, "rubric_version": r.rubric_version}
        for r in rows
    ]
