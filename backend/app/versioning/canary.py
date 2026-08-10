"""Canary routing: experiments route a fraction of chat traffic to RAG version B.

Version B at the moment differs by prompt version + model config; the routing
decision is deterministic per conversation for stability."""

import hashlib

from sqlalchemy.orm import Session

from app.models.versioning import Experiment


def route_version(db: Session, user_id: str, conversation_id: str | None = None) -> tuple[str, str | None]:
    """Returns (rag_version, prompt_version_override)."""
    experiment = db.query(Experiment).filter(Experiment.is_active.is_(True)).first()
    if not experiment:
        return "v1", None
    key = f"{user_id}:{conversation_id or 'new'}"
    h = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 100
    if h < experiment.traffic_percent_b:
        return experiment.rag_version_b, None
    return experiment.rag_version_a, None
