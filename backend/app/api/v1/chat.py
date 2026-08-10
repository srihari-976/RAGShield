"""RAG chat: ACL-filtered retrieval -> grounded prompt -> Ollama -> SSE stream.

Security flow: identity -> authorization filter -> retrieval (only authorized
chunks) -> final ACL verification -> prompt -> LLM.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.authorization import AuthorizationService
from app.auth.dependencies import get_authz_service, get_current_user
from app.auth.rbac import Identity
from app.core.database import get_db
from app.generation.gateway import (
    build_prompt,
    chat_completion,
    get_active_chat_model,
    get_active_prompt,
    get_chunk_texts,
    stream_ollama,
)
from app.generation.grounding import verify_answer
from app.models.chat import Conversation, Message
from app.observability.audit import log_action
from app.observability.tracing import Tracer, new_request_id, record_span
from app.retrieval.service import RetrievalService
from app.schemas.schemas import ChatRequest, ConversationSummary, MessageSummary, CitationRef
from app.versioning.canary import route_version

router = APIRouter(prefix="/chat", tags=["chat"])


def _conv_summary(c: Conversation) -> ConversationSummary:
    return ConversationSummary(
        id=c.id, tenant_id=c.tenant_id, user_id=c.user_id, title=c.title,
        model=c.model, rag_version=c.rag_version, created_at=c.created_at,
    )


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    identity: Identity = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == identity.user_id, Conversation.tenant_id == identity.tenant_id)
        .order_by(Conversation.updated_at.desc())
        .limit(50)
        .all()
    )
    return [_conv_summary(c) for c in convs]


@router.get("/conversations/{conversation_id}", response_model=list[MessageSummary])
def get_conversation(
    conversation_id: str,
    identity: Identity = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.tenant_id == identity.tenant_id,
        Conversation.user_id == identity.user_id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    return [_msg_summary(m) for m in conv.messages]


def _msg_summary(m: Message) -> MessageSummary:
    citations: list[CitationRef] = []
    grounded = m.grounded
    try:
        meta = json.loads(m.metadata_json or "{}")
        for c in meta.get("citations", []):
            citations.append(
                CitationRef(index=c["index"], document_id=c["document_id"], chunk_id=c.get("chunk_id", ""), document_title="")
            )
    except json.JSONDecodeError:
        meta = {}
    return MessageSummary(
        id=m.id, role=m.role, content=m.content, grounded=grounded,
        abstained=m.abstained, citations=citations, latency_ms=m.latency_ms, created_at=m.created_at,
    )


def _build_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _sse_loop(
    identity: Identity,
    db: Session,
    question: str,
    model: str | None,
    conversation_id: str | None,
    request_id: str,
) -> AsyncGenerator[str, None]:
    tracer = Tracer(db, identity.tenant_id, request_id, identity.user_id)
    started = time.perf_counter()
    rag_version, _ = route_version(db, identity.user_id, conversation_id)

    try:
        with tracer.span("retrieval"):
            authz = AuthorizationService(db)
            retriever = RetrievalService(db, authz, identity)
            result = retriever.retrieve(question)
        chunks = result["chunks"]
        if result["denied_chunk_ids"]:
            log_action(
                db, identity.tenant_id, "acl_denial", user_id=identity.user_id, query_text=question,
                decision="denied", reason=f"{len(result['denied_chunk_ids'])} chunks blocked by ACL verification",
                metadata={"denied_chunks": result["denied_chunk_ids"]},
            )
        yield _build_event("retrieval", {
            "chunk_count": len(chunks),
            "denied_chunk_ids": result["denied_chunk_ids"],
            "timings": result["timings"],
        })

        if not chunks:
            yield _build_event("token", {"text": "I don't have any authorized information to answer this question.", "done": False})
            yield _build_event("token", {"text": "", "done": True})
            yield _build_event("done", {"grounded": True, "abstained": True, "citations": [], "latency_ms": int((time.perf_counter() - started) * 1000), "rag_version": rag_version})
            return

        prompt = get_active_prompt(db)
        model = model or get_active_chat_model(db)
        messages, citations = build_prompt(question, chunks, prompt, identity)

        conv = None
        if conversation_id:
            conv = db.query(Conversation).filter(
                Conversation.id == conversation_id,
                Conversation.tenant_id == identity.tenant_id,
                Conversation.user_id == identity.user_id,
            ).first()
        if not conv:
            conv = Conversation(
                tenant_id=identity.tenant_id, user_id=identity.user_id,
                title=question[:120], model=model, rag_version=rag_version,
            )
            db.add(conv)
            db.flush()

        db.add(Message(conversation_id=conv.id, role="user", content=question))
        db.commit()

        with tracer.span("llm_stream"):
            full_text = ""
            async for chunk in stream_ollama(messages, model):
                if chunk["type"] == "error":
                    yield _build_event("error", chunk)
                    return
                token = chunk["text"]
                if token:
                    full_text += token
                    yield _build_event("token", {"text": token, "done": False})

        with tracer.span("grounding"):
            chunk_texts = get_chunk_texts(chunks)
            grounding = verify_answer(full_text, chunk_texts)

        latency_ms = int((time.perf_counter() - started) * 1000)
        conv.updated_at = datetime.now(timezone.utc)
        msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=full_text,
            metadata_json=json.dumps({"citations": citations, "grounding": grounding, "model": model, "rag_version": rag_version}),
            latency_ms=latency_ms,
            grounded=grounding["overall_grounded"],
            abstained=grounding.get("abstained", False),
        )
        db.add(msg)
        db.commit()
        log_action(
            db, identity.tenant_id, "chat.query", user_id=identity.user_id, query_text=question,
            metadata={
                "documents_accessed": sorted({c.get("document_id") for c in citations}),
                "rag_version": rag_version, "model": model,
            },
        )
        yield _build_event("done", {
            "grounded": grounding["overall_grounded"],
            "abstained": grounding.get("abstained", False),
            "citations": citations,
            "latency_ms": latency_ms,
            "rag_version": rag_version,
            "conversation_id": conv.id,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        yield _build_event("error", {"detail": str(e)[:300]})
    finally:
        total_ms = int((time.perf_counter() - started) * 1000)
        record_span(db, request_id, "chat_total", total_ms, identity.tenant_id, identity.user_id)
        tracer.flush()


@router.post("/query")
async def chat(
    body: ChatRequest,
    request: Request,
    identity: Identity = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.stream:
        request_id = new_request_id()
        return StreamingResponse(
            _sse_loop(identity, db, body.query, body.model, body.conversation_id, request_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Non-streaming: block until done
    request_id = new_request_id()
    tracer = Tracer(db, identity.tenant_id, request_id, identity.user_id)
    started = time.perf_counter()
    rag_version, _ = route_version(db, identity.user_id, body.conversation_id)
    try:
        with tracer.span("retrieval"):
            authz = AuthorizationService(db)
            retriever = RetrievalService(db, authz, identity)
            result = retriever.retrieve(body.query)
        chunks = result["chunks"]
        if result["denied_chunk_ids"]:
            log_action(
                db, identity.tenant_id, "acl_denial", user_id=identity.user_id, query_text=body.query,
                decision="denied", reason=f"{len(result['denied_chunk_ids'])} chunks blocked by ACL verification",
                metadata={"denied_chunks": result["denied_chunk_ids"]},
            )
        if not chunks:
            with tracer.span("grounding"):
                pass
            return {"answer": "I don't have any authorized information to answer this question.", "grounded": True, "abstained": True, "citations": [], "rag_version": rag_version}
        with tracer.span("llm_stream"):
            conv, msg, meta = await chat_completion(db, identity, body.query, chunks, body.model, body.conversation_id)
        with tracer.span("grounding"):
            pass
        log_action(
            db, identity.tenant_id, "chat.query", user_id=identity.user_id, query_text=body.query,
            metadata={
                "documents_accessed": sorted({c.get("document_id") for c in meta["citations"]}),
                "rag_version": rag_version, "model": conv.model,
            },
        )
        return {
            "answer": msg.content,
            "grounded": meta["grounding"]["overall_grounded"],
            "abstained": meta["grounding"].get("abstained", False),
            "citations": meta["citations"],
            "conversation_id": conv.id,
            "rag_version": conv.rag_version,
        }
    finally:
        total_ms = int((time.perf_counter() - started) * 1000)
        record_span(db, request_id, "chat_total", total_ms, identity.tenant_id, identity.user_id)
        tracer.flush()
