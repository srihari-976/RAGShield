"""Lightweight in-house tracing: every request records per-stage spans to the
traces table, plus latency percentiles computed from recent spans."""

import json
import time
import uuid
from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session

from app.models.observability import TraceSpan


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def record_span(
    db: Session,
    request_id: str,
    span_name: str,
    duration_ms: int,
    tenant_id: str,
    user_id: str | None = None,
    status: str = "ok",
    metadata: dict[str, Any] | None = None,
    commit: bool = True,
) -> None:
    db.add(
        TraceSpan(
            tenant_id=tenant_id,
            user_id=user_id,
            request_id=request_id,
            span_name=span_name,
            duration_ms=duration_ms,
            status=status,
            metadata_json=json.dumps(metadata or {}),
        )
    )
    if commit:
        db.commit()


class Tracer:
    def __init__(self, db: Session, tenant_id: str, request_id: str, user_id: str | None = None):
        self.db = db
        self.tenant_id = tenant_id
        self.request_id = request_id
        self.user_id = user_id
        self.spans: list[dict[str, Any]] = []

    @contextmanager
    def span(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
            status = "ok"
        except Exception:
            status = "error"
            raise
        finally:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            self.spans.append({"name": name, "duration_ms": duration_ms, "status": status})

    def flush(self) -> None:
        for s in self.spans:
            record_span(
                self.db,
                self.request_id,
                s["name"],
                s["duration_ms"],
                self.tenant_id,
                self.user_id,
                s["status"],
                commit=False,
            )
        self.db.commit()
        self.spans = []


def latency_percentiles(db: Session, tenant_id: str, hours: int = 24) -> dict[str, Any]:
    import datetime

    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    rows = (
        db.query(TraceSpan.duration_ms)
        .filter(TraceSpan.tenant_id == tenant_id, TraceSpan.created_at >= since, TraceSpan.span_name == "chat_total")
        .all()
    )
    vals = sorted(r[0] for r in rows)
    if not vals:
        return {"p50": None, "p95": None, "p99": None, "count": 0, "error_rate": 0.0}
    n = len(vals)

    def pct(p: float) -> int:
        idx = min(n - 1, int(p * n))
        return vals[idx]

    errors = (
        db.query(TraceSpan)
        .filter(TraceSpan.tenant_id == tenant_id, TraceSpan.created_at >= since, TraceSpan.status == "error")
        .count()
    )
    return {"p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99), "count": n, "error_rate": round(errors / max(n, 1), 4)}
