import logging
import time
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models import (
    AppConfig,
    ChatMessage,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    UploadResponse,
    Workspace,
    WorkspaceCreate,
    WorkspaceMergeRequest,
)
from app.pdf import chunk_page_text, extract_pdf_pages
from app.rag import embed_texts, generate_answer, is_ambiguous_short_reply, retrieve_chunks
from app.storage import (
    append_chunks,
    append_message,
    create_workspace,
    get_workspace,
    load_chunks,
    list_workspaces,
    load_messages,
    workspace_dir,
)

settings = get_settings()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RAG Research Assistant API",
    version="0.2.0",
    docs_url=None if settings.app_env == "production" else "/docs",
    redoc_url=None if settings.app_env == "production" else "/redoc",
)

if settings.trusted_hosts and settings.trusted_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_request_metadata(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-ms"] = f"{(time.perf_counter() - started) * 1000:.2f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error at %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health", response_model=HealthResponse)
def health() -> dict:
    storage_writable = settings.storage_dir.exists() and settings.storage_dir.is_dir()
    return {
        "status": "ok",
        "environment": settings.app_env,
        "storage_writable": storage_writable,
        "llm_enabled": bool(settings.openai_api_key),
    }


@app.get("/config", response_model=AppConfig)
def public_config() -> dict:
    return {
        "app_env": settings.app_env,
        "max_upload_mb": settings.max_upload_mb,
        "max_pdf_pages": settings.max_pdf_pages,
        "max_chunks_per_document": settings.max_chunks_per_document,
        "llm_enabled": bool(settings.openai_api_key),
    }


@app.post("/workspaces", response_model=Workspace)
def create_workspace_endpoint(payload: WorkspaceCreate) -> dict:
    return {**create_workspace(payload.name), "document_count": 0}


@app.get("/workspaces", response_model=list[Workspace])
def list_workspaces_endpoint() -> list[dict]:
    return list_workspaces()


@app.post("/workspaces/merge", response_model=Workspace)
def merge_workspaces(payload: WorkspaceMergeRequest) -> dict:
    source_workspaces = []
    for workspace_id in payload.workspace_ids:
        workspace = get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")
        source_workspaces.append(workspace)

    merged_name = payload.name or "Merged: " + " + ".join(workspace["name"] for workspace in source_workspaces)
    merged = create_workspace(merged_name[:80])
    per_workspace_budget = max(1, payload.total_chunk_budget // len(source_workspaces))
    merged_records: list[dict] = []
    merge_document_id = uuid4().hex

    for workspace in source_workspaces:
        chunks = load_chunks(workspace["id"])[:per_workspace_budget]
        for chunk in chunks:
            merged_records.append(
                {
                    **chunk,
                    "chunk_id": f"{merge_document_id}-{workspace['id']}-{chunk['chunk_id']}",
                    "document_id": chunk.get("document_id", merge_document_id),
                    "source_workspace_id": workspace["id"],
                    "source_workspace_name": workspace["name"],
                }
            )

    if merged_records:
        append_chunks(merged["id"], merged_records)

    append_message(
        merged["id"],
        "system",
        (
            f"Merged {len(source_workspaces)} sessions using up to {per_workspace_budget} chunks from each: "
            + ", ".join(workspace["name"] for workspace in source_workspaces)
            + ". Ask questions here to use the combined session memory."
        ),
    )
    docs = {chunk["document_id"] for chunk in merged_records}
    return {**merged, "document_count": len(docs)}


@app.get("/workspaces/{workspace_id}/messages", response_model=list[ChatMessage])
def list_workspace_messages(workspace_id: str) -> list[dict]:
    if not get_workspace(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    return load_messages(workspace_id)


@app.post("/workspaces/{workspace_id}/documents", response_model=UploadResponse)
async def upload_document(workspace_id: str, file: UploadFile = File(...)) -> dict:
    if not get_workspace(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    filename = Path(file.filename or "document.pdf").name
    if len(filename) > 180:
        raise HTTPException(status_code=400, detail="Filename is too long")
    if file.content_type != "application/pdf" and not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    document_id = uuid4().hex
    upload_dir = workspace_dir(workspace_id) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = upload_dir / f"{document_id}.pdf"

    size = 0
    first_chunk = True
    try:
        with pdf_path.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                if first_chunk:
                    first_chunk = False
                    if not chunk.startswith(b"%PDF-"):
                        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF")
                size += len(chunk)
                if size > settings.upload_limit_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"PDF is too large. Maximum upload size is {settings.max_upload_mb} MB.",
                    )
                target.write(chunk)
    except HTTPException:
        pdf_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if size == 0:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty")

    pages = extract_pdf_pages(Path(pdf_path), max_pages=settings.max_pdf_pages)
    records: list[dict] = []
    texts: list[str] = []
    for page in pages:
        for chunk_index, text in enumerate(chunk_page_text(page)):
            if len(records) >= settings.max_chunks_per_document:
                break
            records.append(
                {
                    "chunk_id": f"{document_id}-{page.page}-{chunk_index}",
                    "document_id": document_id,
                    "filename": filename,
                    "page": page.page,
                    "text": text,
                }
            )
            texts.append(text)
        if len(records) >= settings.max_chunks_per_document:
            break

    if not records:
        raise HTTPException(status_code=422, detail="No readable text found in this PDF")

    try:
        embeddings = embed_texts(settings, texts)
    except Exception as exc:
        logger.exception("Embedding failed for workspace %s", workspace_id)
        raise HTTPException(status_code=502, detail="Could not generate embeddings for this PDF") from exc

    for record, embedding in zip(records, embeddings):
        record["embedding"] = embedding

    append_chunks(workspace_id, records)
    append_message(
        workspace_id,
        "system",
        f"Indexed {filename}: {len(pages)} pages, {len(records)} chunks.",
    )
    return {
        "document_id": document_id,
        "filename": filename,
        "pages": len(pages),
        "chunks": len(records),
    }


@app.post("/workspaces/{workspace_id}/query", response_model=QueryResponse)
def query_workspace(workspace_id: str, payload: QueryRequest) -> dict:
    if not get_workspace(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")

    chunks = load_chunks(workspace_id)
    if not chunks:
        raise HTTPException(status_code=400, detail="Upload at least one PDF before asking questions")

    if is_ambiguous_short_reply(payload.question):
        answer = (
            "Please ask a complete question about the uploaded paper, for example: "
            "'What is the paper about?' or 'Summarize the main contributions.'"
        )
        append_message(workspace_id, "user", payload.question)
        append_message(workspace_id, "assistant", answer)
        return {
            "answer": answer,
            "sources": [],
        }

    try:
        top_chunks = retrieve_chunks(settings, chunks, payload.question, payload.top_k)
        answer = generate_answer(settings, payload.question, top_chunks)
    except Exception as exc:
        logger.exception("Query failed for workspace %s", workspace_id)
        raise HTTPException(status_code=502, detail="Could not generate an answer right now") from exc

    sources = [
        {
            "document_id": chunk["document_id"],
            "filename": chunk["filename"],
            "page": chunk["page"],
            "chunk_id": chunk["chunk_id"],
            "score": round(float(chunk["score"]), 4),
            "text": chunk["text"],
        }
        for chunk in top_chunks
    ]
    append_message(workspace_id, "user", payload.question)
    append_message(workspace_id, "assistant", answer, sources)
    return {"answer": answer, "sources": sources}
