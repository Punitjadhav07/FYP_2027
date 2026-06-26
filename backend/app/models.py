from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class Workspace(BaseModel):
    id: str
    name: str
    document_count: int = 0


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
    sources: list[Source] = []
    created_at: str


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    pages: int
    chunks: int
