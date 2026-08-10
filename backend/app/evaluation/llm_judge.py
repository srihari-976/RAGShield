"""LLM-as-judge generation quality metrics: groundedness, completeness,
relevance scored 0-1 from the answer + authorized evidence."""

import json
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

JUDGE_PROMPT = """You are an evaluation judge. Score the answer to a question using ONLY the provided evidence.

Question: {question}

Evidence:
{evidence}

Answer:
{answer}

Respond with ONLY JSON: {{
  "groundedness": 0.0-1.0,  (are claims in the answer supported by evidence?)
  "completeness": 0.0-1.0,  (does it answer all parts of the question?)
  "relevance": 0.0-1.0      (does it stay on topic?)
}}
"""


def judge_answer(question: str, answer: str, evidence_texts: list[str], model: str | None = None) -> dict[str, float]:
    evidence = "\n\n".join(f"[{i + 1}] {t[:1500]}" for i, t in enumerate(evidence_texts)) or "(none)"
    prompt = JUDGE_PROMPT.format(question=question, evidence=evidence, answer=answer[:4000])
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{settings.ollama_base_url}/api/generate",
                json={
                    "model": model or settings.chat_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_ctx": 4096, "temperature": 0, "num_predict": 200},
                },
            )
        text = resp.json().get("response", "")
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start : end + 1]) if start >= 0 and end > start else {}
        return {
            "groundedness": float(data.get("groundedness", 0.0)),
            "completeness": float(data.get("completeness", 0.0)),
            "relevance": float(data.get("relevance", 0.0)),
        }
    except Exception as e:
        logger.warning("LLM judge failed: %s", e)
        return {"groundedness": 0.0, "completeness": 0.0, "relevance": 0.0}
