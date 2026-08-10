"""Grounding pass: verify answer claims against authorized evidence.

Two modes:
- heuristic (default): each citation's chunk text must share significant
  lexical content with the sentence it cites (fast, no extra LLM call).
- llm: LLM-judge extraction + verification via GROUNDING_PROMPT.
"""

import json
import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_ABSTAIN_PATTERNS = [
    re.compile(r"i can['\u2019]t provide that information", re.I),
    re.compile(r"cannot (answer|determine|provide)", re.I),
    re.compile(r"no authorized evidence", re.I),
    re.compile(r"insufficient (evidence|information)", re.I),
]


def _norm(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if len(t) > 3}


def _overlap_ratio(claim: str, chunk_text: str) -> float:
    a, b = _norm(claim), _norm(chunk_text)
    if not a:
        return 0.0
    return len(a & b) / len(a)


def is_abstention(answer: str) -> bool:
    return any(p.search(answer) for p in _ABSTAIN_PATTERNS)


def verify_answer_heuristic(answer: str, citations: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify each cited claim against its chunk text by lexical overlap."""
    verdicts: list[dict[str, Any]] = []
    sentences = re.split(r"(?<=[.!?])\s+", answer)
    for i, citation in enumerate(citations, start=1):
        chunk_text = citation.get("chunk_text", "")
        supported = False
        for sent in sentences:
            if f"[{i}]" not in sent:
                continue
            if _overlap_ratio(sent, chunk_text) >= 0.30:
                supported = True
            break
        verdicts.append({"citation": i, "document_id": citation.get("document_id"), "supported": supported})
    grounded = all(v["supported"] for v in verdicts) if verdicts else True
    return {"mode": "heuristic", "verdicts": verdicts, "overall_grounded": grounded, "abstained": is_abstention(answer)}


def verify_answer_llm(answer: str, citations: list[dict[str, Any]], model: str | None = None) -> dict[str, Any]:
    from app.generation.prompts import GROUNDING_PROMPT_V1

    evidence = "\n\n".join(
        f"[{i}] {c.get('chunk_text', '')[:1500]}" for i, c in enumerate(citations, start=1)
    )
    prompt = GROUNDING_PROMPT_V1.format(question="(see conversation)", answer=answer, evidence=evidence)
    try:
        with httpx.Client(timeout=90) as client:
            resp = client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": model or settings.chat_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_ctx": 4096, "temperature": 0, "num_predict": 600},
                },
            )
        text = resp.json().get("response", "")
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start : end + 1]) if start >= 0 and end > start else {}
        verdicts = data.get("claims", [])
        overall = bool(data.get("overall_grounded", True))
        return {
            "mode": "llm",
            "verdicts": verdicts,
            "overall_grounded": overall,
            "abstained": is_abstention(answer),
        }
    except Exception as e:
        logger.warning("LLM grounding check failed, falling back to heuristic: %s", e)
        return verify_answer_heuristic(answer, citations)


def verify_answer(answer: str, citations: list[dict[str, Any]], mode: str | None = None) -> dict[str, Any]:
    mode = mode or settings.grounding_mode
    if mode == "llm":
        return verify_answer_llm(answer, citations)
    return verify_answer_heuristic(answer, citations)
