from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models import QueryRequest, QueryResponse, UploadResponse, Workspace, WorkspaceCreate
from app.pdf import chunk_page_text, extract_pdf_pages
from app.rag import embed_texts, generate_answer, is_ambiguous_short_reply, retrieve_chunks
from app.storage import append_chunks, create_workspace, get_workspace, list_workspaces, workspace_dir

settings = get_settings()

app = FastAPI(title="RAG Research Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/workspaces", response_model=Workspace)
def create_workspace_endpoint(payload: WorkspaceCreate) -> dict:
    return {**create_workspace(payload.name), "document_count": 0}


@app.get("/workspaces", response_model=list[Workspace])
def list_workspaces_endpoint() -> list[dict]:
    return list_workspaces()


@app.post("/workspaces/{workspace_id}/documents", response_model=UploadResponse)
async def upload_document(workspace_id: str, file: UploadFile = File(...)) -> dict:
    if not get_workspace(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    document_id = uuid4().hex
    upload_dir = workspace_dir(workspace_id) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = upload_dir / f"{document_id}.pdf"
    pdf_path.write_bytes(await file.read())

    pages = extract_pdf_pages(Path(pdf_path))
    records: list[dict] = []
    texts: list[str] = []
    for page in pages:
        for chunk_index, text in enumerate(chunk_page_text(page)):
            records.append(
                {
                    "chunk_id": f"{document_id}-{page.page}-{chunk_index}",
                    "document_id": document_id,
                    "filename": file.filename,
                    "page": page.page,
                    "text": text,
                }
            )
            texts.append(text)

    if not records:
        raise HTTPException(status_code=422, detail="No readable text found in this PDF")

    embeddings = embed_texts(settings, texts)
    for record, embedding in zip(records, embeddings):
        record["embedding"] = embedding

    append_chunks(workspace_id, records)
    return {
        "document_id": document_id,
        "filename": file.filename,
        "pages": len(pages),
        "chunks": len(records),
    }


@app.post("/workspaces/{workspace_id}/query", response_model=QueryResponse)
def query_workspace(workspace_id: str, payload: QueryRequest) -> dict:
    if not get_workspace(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")

    from app.storage import load_chunks

    chunks = load_chunks(workspace_id)
    if not chunks:
        raise HTTPException(status_code=400, detail="Upload at least one PDF before asking questions")

    if is_ambiguous_short_reply(payload.question):
        return {
            "answer": (
                "Please ask a complete question about the uploaded paper, for example: "
                "'What is the paper about?' or 'Summarize the main contributions.'"
            ),
            "sources": [],
        }

    top_chunks = retrieve_chunks(settings, chunks, payload.question, payload.top_k)
    answer = generate_answer(settings, payload.question, top_chunks)
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
    return {"answer": answer, "sources": sources}
