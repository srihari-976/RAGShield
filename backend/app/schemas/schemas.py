from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.document import CLASSIFICATIONS, DOCUMENT_STATUSES


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserSummary"


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None
    department: str | None = None
    roles: list[str] = Field(default_factory=list)
    tenant_id: str | None = None  # only honored with tenant.manage permission


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    department: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)
    roles: list[str] | None = None


class UserSummary(BaseModel):
    id: str
    tenant_id: str
    username: str
    email: str
    full_name: str | None
    department: str | None
    is_active: bool
    roles: list[str] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    admin_username: str | None = Field(default=None, min_length=3, max_length=80)
    admin_password: str | None = Field(default=None, min_length=8)
    admin_email: EmailStr | None = None


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    is_active: bool | None = None


class TenantSummary(BaseModel):
    id: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    user_count: int = 0
    document_count: int = 0

    model_config = {"from_attributes": True}


class RoleSummary(BaseModel):
    id: str
    name: str
    description: str | None
    is_system: bool
    permissions: list[str] = []

    model_config = {"from_attributes": True}


class DocumentCreate(BaseModel):
    title: str | None = None
    document_type: str = "general"
    classification: str = Field(default="internal", pattern="|".join(CLASSIFICATIONS))
    owner_id: str | None = None


class DocumentSummary(BaseModel):
    id: str
    tenant_id: str
    title: str
    document_type: str
    owner_id: str | None
    classification: str
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    error_message: str | None
    chunk_count: int
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentPermissionCreate(BaseModel):
    document_id: str
    action: str = "read"
    principal_type: str  # user | role | everyone
    principal_id: str | None = None


class DocumentPermissionSummary(BaseModel):
    id: str
    document_id: str
    action: str
    principal_type: str
    principal_id: str | None

    model_config = {"from_attributes": True}


class PolicyCreate(BaseModel):
    name: str
    description: str | None = None
    action: str = "read"
    rule: str
    effect: str = "allow"
    priority: int = 100
    is_active: bool = True


class PolicySummary(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: str | None
    action: str
    rule: str
    effect: str
    priority: int
    is_active: bool

    model_config = {"from_attributes": True}


class ConversationSummary(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    title: str
    model: str | None
    rag_version: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    query: str = Field(min_length=1, max_length=4000)
    model: str | None = None
    stream: bool = True


class CitationRef(BaseModel):
    index: int
    document_id: str
    chunk_id: str
    document_title: str


class MessageSummary(BaseModel):
    id: str
    role: str
    content: str
    grounded: bool | None
    abstained: bool
    citations: list[CitationRef] = []
    latency_ms: int | None
    created_at: datetime


class GoldenQuestionCreate(BaseModel):
    question: str
    expected_document_ids: list[str]
    category: str | None = None


class EvaluationRunCreate(BaseModel):
    name: str
    rag_version: str = "v1"
    prompt_version: str = "v1"
    retriever_config: dict | None = None


class RatingCreate(BaseModel):
    item_id: str
    groundedness: int | None = Field(default=None, ge=1, le=5)
    relevance: int | None = Field(default=None, ge=1, le=5)
    completeness: int | None = Field(default=None, ge=1, le=5)
    citation_quality: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = None


class AdjudicationCreate(BaseModel):
    item_id: str
    dimension: str
    final_score: int = Field(ge=1, le=5)
    reason: str | None = None


class PromptVersionCreate(BaseModel):
    version: str
    system_prompt: str
    grounding_prompt: str | None = None


class ExperimentCreate(BaseModel):
    name: str
    rag_version_a: str
    rag_version_b: str
    traffic_percent_b: float = 5.0


class ModelConfigUpdate(BaseModel):
    chat_model: str | None = None
    embedding_model: str | None = None
