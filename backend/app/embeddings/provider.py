import httpx

from app.core.config import get_settings

settings = get_settings()


class EmbeddingError(Exception):
    pass


class OllamaEmbeddingProvider:
    """EmbeddingProvider over Ollama's /api/embed. Model is configurable."""

    def __init__(self, model: str | None = None, base_url: str | None = None, timeout: float = 120.0):
        self.model = model or settings.embedding_model
        self.base_url = base_url or settings.ollama_base_url
        self.timeout = timeout

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": texts},
            )
            if resp.status_code != 200:
                raise EmbeddingError(f"Ollama embed failed: {resp.status_code} {resp.text[:300]}")
        data = resp.json()
        return data["embeddings"]

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def dimension(self) -> int:
        probe = self.embed_text("probe")
        return len(probe)


def get_embedding_provider(model: str | None = None) -> OllamaEmbeddingProvider:
    return OllamaEmbeddingProvider(model=model)
