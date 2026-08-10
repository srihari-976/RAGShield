from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.tenant import new_uuid, utcnow


class GoldenQuestion(Base):
    """Offline evaluation golden set: question -> expected document ids."""

    __tablename__ = "golden_questions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_document_ids: Mapped[str] = mapped_column(Text, nullable=False)  # JSON list
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rag_version: Mapped[str] = mapped_column(String(40), default="v1")
    prompt_version: Mapped[str] = mapped_column(String(40), default="v1")
    retriever_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    created_by: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items = relationship("EvaluationItem", back_populates="run", cascade="all, delete-orphan")


class EvaluationItem(Base):
    __tablename__ = "evaluation_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("evaluation_runs.id"), index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_document_ids: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    expected_document_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    recall_at_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision_at_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    mrr: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndcg: Mapped[float | None] = mapped_column(Float, nullable=True)
    groundedness: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    run = relationship("EvaluationRun", back_populates="items")


class Rater(Base):
    __tablename__ = "raters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_adjudicator: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Rating(Base):
    __tablename__ = "ratings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    item_id: Mapped[str] = mapped_column(String(32), ForeignKey("evaluation_items.id"), index=True)
    rater_id: Mapped[str] = mapped_column(String(32), ForeignKey("raters.id"), index=True)
    rubric_version: Mapped[str] = mapped_column(String(40), default="v1")
    groundedness: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    relevance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completeness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citation_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Adjudication(Base):
    __tablename__ = "adjudications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    item_id: Mapped[str] = mapped_column(String(32), ForeignKey("evaluation_items.id"), index=True)
    dimension: Mapped[str] = mapped_column(String(30), nullable=False)
    adjudicator_id: Mapped[str] = mapped_column(String(32), ForeignKey("raters.id"))
    original_scores: Mapped[str] = mapped_column(Text, nullable=False)  # JSON {rater: score}
    final_score: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rubric_version: Mapped[str] = mapped_column(String(40), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

