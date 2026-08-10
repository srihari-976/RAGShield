"""RAG gateway: builds grounded prompts from authorized evidence and streams
Ollama responses. The evidence list handed to this module is ALREADY
authorized (see retrieval.service)."""

import json
import time
from typing import AsyncGenerator

import httpx
from sqlalchemy.orm import Session

from app.auth.rbac import Identity
from app.core.config import get_settings
from app.generation.grounding import verify_answer
from app.generation.prompts import DEFAULT_SYSTEM_PROMPT
from app.models.chat import Conversation, Message
from app.models.document import Document
from app.models.versioning import ModelConfig, PromptVersion

settings = get_settings()


def build_prompt(
    question: str,
    chunks: list[dict],
    system_prompt: str | None = None,
    identity: Identity | None = None,
) -> tuple[str, list[dict]]:
    """Builds the grounded prompt. Returns (full_messages, citation_map)."""
    sp = system_prompt or DEFAULT_SYSTEM_PROMPT
    evidence = "\n\n".join(f"[{i + 1}] {c['payload'].get('text', '')}" for i, c in enumerate(chunks))
    citations = [
        {
            "index": i + 1,
            "document_id": c["payload"].get("document_id"),
            "chunk_id": c.get("chunk_id"),
        }
        for i, c in enumerate(chunks)
    ]
    user_context = ""
    if identity:
        name = identity.full_name or identity.username
        user_context = (
            f"\nCurrent user: {name} (username {identity.username}, roles: {', '.join(identity.roles)}). "
            "Treat this person's own private records as accessible to them.\n"
        )
    user_content = (
        "Evidence (authorized context):\n<evidence>\n" + evidence + "\n</evidence>"
        + user_context
        + "\nQuestion: " + question
    )
    messages = [
        {"role": "system", "content": sp},
        {"role": "user", "content": user_content},
    ]
    return messages, citations


def get_chunk_texts(chunks: list[dict]) -> list[dict]:
    return [{"chunk_id": c.get("chunk_id"), "document_id": c["payload"].get("document_id"), "chunk_text": c["payload"].get("text", "")} for c in chunks]


async def stream_ollama(messages: list[dict], model: str) -> AsyncGenerator[dict, None]:
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"num_ctx": 4096, "temperature": 0.2, "num_predict": 600},
    }
    async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
        async with client.stream("POST", f"{settings.ollama_base_url}/api/chat", json=payload) as resp:
            if resp.status_code != 200:
                text = (await resp.aread()).decode(errors="replace")
                yield {"type": "error", "detail": f"ollama error {resp.status_code}: {text[:300]}"}
                return
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield {"type": "token", "text": chunk.get("message", {}).get("content", ""), "done": chunk.get("done", False)}


def get_active_prompt(db: Session) -> str:
    pv = db.query(PromptVersion).filter(PromptVersion.is_active.is_(True)).order_by(PromptVersion.created_at.desc()).first()
    return pv.system_prompt if pv else DEFAULT_SYSTEM_PROMPT


def get_active_chat_model(db: Session) -> str:
    mc = db.query(ModelConfig).filter(ModelConfig.kind == "chat", ModelConfig.is_default.is_(True)).first()
    return mc.model if mc else settings.chat_model


async def chat_completion(
    db: Session,
    identity: Identity,
    question: str,
    chunks: list[dict],
    model: str | None = None,
    conversation_id: str | None = None,
) -> tuple[Conversation, Message, dict]:
    """Non-streaming completion for evaluation runs."""
    prompt = get_active_prompt(db)
    model = model or get_active_chat_model(db)
    messages, citations = build_prompt(question, chunks, prompt, identity)

    conv = None
    if conversation_id:
        conv = db.query(Conversation).filter(
            Conversation.id == conversation_id, Conversation.tenant_id == identity.tenant_id
        ).first()
    if not conv:
        conv = Conversation(tenant_id=identity.tenant_id, user_id=identity.user_id, title=question[:120], model=model)
        db.add(conv)
        db.flush()

    t0 = time.perf_counter()
    full_text = ""
    async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"num_ctx": 4096, "temperature": 0.2, "num_predict": 600},
            },
        )
    data = resp.json()
    full_text = data.get("message", {}).get("content", "")
    latency_ms = int((time.perf_counter() - t0) * 1000)

    chunk_texts = get_chunk_texts(chunks)
    grounding = verify_answer(full_text, chunk_texts)

    msg = Message(
        conversation_id=conv.id,
        role="assistant",
        content=full_text,
        metadata_json=json.dumps({"citations": citations, "grounding": grounding, "model": model}),
        latency_ms=latency_ms,
        grounded=grounding["overall_grounded"],
        abstained=grounding.get("abstained", False),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return conv, msg, {"citations": citations, "grounding": grounding}


def load_documents_for_citations(db: Session, citations: list[dict]) -> dict[str, str]:
    ids = [c["document_id"] for c in citations if c.get("document_id")]
    if not ids:
        return {}
    docs = db.query(Document).filter(Document.id.in_(ids)).all()
    return {d.id: d.title for d in docs}
