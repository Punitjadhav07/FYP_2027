from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Workspace name is required")
        return cleaned


class Workspace(BaseModel):
    id: str
    name: str
    document_count: int = 0


class WorkspaceStats(BaseModel):
    id: str
    name: str
    document_count: int
    chunk_count: int
    approx_tokens: int


class UserPublic(BaseModel):
    id: str
    email: str
    name: str


class AuthRequest(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=6, max_length=128)
    name: str | None = Field(default=None, max_length=80)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned:
            raise ValueError("Enter a valid email")
        return cleaned

    @field_validator("name")
    @classmethod
    def normalize_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


class WorkspaceMergeRequest(BaseModel):
    workspace_ids: list[str] = Field(min_length=2, max_length=6)
    name: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("workspace_ids")
    @classmethod
    def unique_workspace_ids(cls, value: list[str]) -> list[str]:
        unique = list(dict.fromkeys(value))
        if len(unique) < 2:
            raise ValueError("Select at least two unique sessions to merge")
        return unique

    @field_validator("name")
    @classmethod
    def normalize_merge_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Merge name cannot be empty")
        return cleaned


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1200)
    top_k: int = Field(default=5, ge=1, le=10)


class Source(BaseModel):
    document_id: str
    filename: str
    page: int
    chunk_id: str
    score: float
    text: str


class Citation(BaseModel):
    label: str
    document_id: str
    filename: str
    page: int
    chunk_id: str
    score: float
    text: str
    citation: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]
    citations: list[Citation] = Field(default_factory=list)


class SummaryRequest(BaseModel):
    focus: str | None = Field(default=None, max_length=240)
    top_k: int = Field(default=8, ge=4, le=12)


class SummaryResponse(BaseModel):
    summary: str
    sources: list[Source]
    citations: list[Citation] = Field(default_factory=list)


class ChatMessage(BaseModel):
    id: str
    role: str
    text: str
    sources: list[Source] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    created_at: str


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    pages: int
    chunks: int


class AppConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    app_env: str
    max_upload_mb: int
    max_pdf_pages: int
    max_chunks_per_document: int
    default_query_sources: int
    default_summary_sources: int
    default_merge_chunk_budget: int
    google_enabled: bool
    llm_enabled: bool


class HealthResponse(BaseModel):
    status: str
    environment: str
    storage_writable: bool
    llm_enabled: bool
