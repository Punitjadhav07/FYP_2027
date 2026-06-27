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


class WorkspaceMergeRequest(BaseModel):
    workspace_ids: list[str] = Field(min_length=2, max_length=6)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    total_chunk_budget: int = Field(default=80, ge=10, le=300)

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


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]


class ChatMessage(BaseModel):
    id: str
    role: str
    text: str
    sources: list[Source] = Field(default_factory=list)
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
    llm_enabled: bool


class HealthResponse(BaseModel):
    status: str
    environment: str
    storage_writable: bool
    llm_enabled: bool
