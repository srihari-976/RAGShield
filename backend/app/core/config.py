from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "RAGShield"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://ragshield:ragshield@localhost:5432/ragshield"

    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "enterprise_documents"

    ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "qwen3-embedding:8b"
    chat_model: str = "qwen3.5:9b"
    embedding_dim: int = 1024
    ollama_timeout: float = 300.0

    file_storage_path: str = "./data/files"

    chunk_size: int = 600
    chunk_overlap: int = 80
    upload_max_mb: int = 50

    grounding_mode: str = "heuristic"

    rate_limit_per_minute: int = 60

    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "admin123"
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_tenant_name: str = "Default"

    hybrid_top_k: int = 20
    rerank_top_k: int = 5
    reranker_enabled: bool = False

    evaluation_gate_recall_at_5: float = 0.90
    evaluation_gate_precision_at_5: float = 0.80
    evaluation_gate_groundedness: float = 0.90
    evaluation_gate_completeness: float = 0.85
    evaluation_gate_p95_seconds: float = 5.0

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
