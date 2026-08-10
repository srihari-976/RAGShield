"""LLM-based reranker over Ollama. Optional; falls back to fusion order."""

import httpx

from app.core.config import get_settings

settings = get_settings()

RERANK_PROMPT = """Given the user question, rank the following evidence passages by relevance.

Question: {question}

Passages:
{passages}

Respond with ONLY a JSON array of passage numbers (1-based) in descending order of relevance, e.g. [2,1,3].
"""


class OllamaReranker:
    def __init__(self, model: str | None = None, base_url: str | None = None, enabled: bool | None = None):
        self.model = model or settings.chat_model
        self.base_url = base_url or settings.ollama_base_url
        self.enabled = settings.reranker_enabled if enabled is None else enabled

    def rerank(self, question: str, items: list[dict], top_k: int) -> list[dict]:
        if not self.enabled or len(items) <= 1:
            return items[:top_k]
        passages = "\n\n".join(
            f"[{i + 1}] {item['payload'].get('text', '')[:1200]}" for i, item in enumerate(items)
        )
        prompt = RERANK_PROMPT.format(question=question, passages=passages)
        try:
            with httpx.Client(timeout=90) as client:
                resp = client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"num_ctx": 4096, "temperature": 0, "num_predict": 120},
                    },
                )
            if resp.status_code != 200:
                return items[:top_k]
            text = resp.json().get("response", "")
            import json

            start, end = text.find("["), text.rfind("]")
            order = json.loads(text[start : end + 1]) if start >= 0 and end > start else None
            if not isinstance(order, list):
                return items[:top_k]
            by_idx = {i + 1: item for i, item in enumerate(items)}
            ranked: list[dict] = []
            seen: set[int] = set()
            for i in order:
                try:
                    n = int(i)
                except (TypeError, ValueError):
                    continue
                if 1 <= n <= len(items) and n not in seen:
                    ranked.append(by_idx[n])
                    seen.add(n)
            ranked += [item for i, item in enumerate(items) if (i + 1) not in seen]
            return ranked[:top_k]
        except Exception:
            return items[:top_k]
