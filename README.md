# Multi-Agent RAG Research Assistant

A web-based research assistant for uploading academic PDFs, indexing their content, and asking source-grounded questions over the uploaded papers.

This repository currently contains the MVP for:

- Workspace creation
- PDF upload and text extraction
- Local chunking and indexing
- Basic retrieval-based Q&A
- Source snippets with page references
- Summary-style questions such as `brief me about this paper`
- Per-workspace conversation history saved locally
- Dark dashboard UI with workspace metrics and score education
- Session memory merge across multiple workspaces
- Local fallback mode when no OpenAI key is configured or OpenAI quota is unavailable

## Project Structure

```txt
.
├── backend/
│   ├── app/
│   │   ├── config.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── pdf.py
│   │   ├── rag.py
│   │   └── storage.py
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   └── styles.css
│   ├── index.html
│   └── package.json
└── README.md
```

## Requirements

- Python 3.10 to 3.13 recommended
- Node.js 18+
- npm
- Git

Note: Python 3.14 may fail with some current FastAPI/Pydantic dependencies. Use Python 3.10-3.13 for smoother setup.

## Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `backend/.env` and add your API key if you want LLM-generated answers:

```env
APP_ENV=development
OPENAI_API_KEY=your_key_here
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
FRONTEND_ORIGIN=http://localhost:5173
CORS_ORIGINS=http://localhost:5173
ALLOWED_HOSTS=*
MAX_UPLOAD_MB=25
MAX_PDF_PAGES=80
MAX_CHUNKS_PER_DOCUMENT=1200
```

The app still works without `OPENAI_API_KEY` using local fallback retrieval and extractive answers. If OpenAI returns a quota or API error, the backend automatically falls back to local embeddings and extractive answers instead of failing the upload or query.

Start the backend:

```bash
uvicorn app.main:app --reload --port 8000
```

If file watching causes OS permission issues, run without reload:

```bash
uvicorn app.main:app --port 8000
```

Backend health check:

```txt
http://127.0.0.1:8000/health
```

Runtime configuration check:

```txt
http://127.0.0.1:8000/config
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open:

```txt
http://127.0.0.1:5173/
```

## Team Workflow

1. Clone the repository.
2. Create your own `backend/.env` from `backend/.env.example`.
3. Never commit `.env`, virtual environments, uploaded PDFs, generated storage, or `node_modules`.
4. Create a branch for each feature or fix.
5. Open a pull request before merging to `main`.

Suggested branch names:

```txt
feature/pdf-ingestion
feature/ragas-scoring
feature/arxiv-import
fix/upload-error-message
docs/update-prd
```

## Current MVP Features

- Create and select workspaces
- Upload PDF papers
- Extract text using PyMuPDF
- Chunk text into searchable passages
- Store indexed chunks locally under ignored backend storage
- Save each workspace conversation locally
- Ask questions about uploaded PDFs
- View retrieved source snippets and page numbers
- View a dark dashboard with document count, answer count, source count, average retrieval score, and score guidance
- Select multiple sessions and merge their memory into a new workspace
- Ask summary prompts like:

```txt
brief me about this paper
what is the paper about
summarize the main contributions
```

## Session Memory Merge

The sidebar includes a `Session memory` panel. Select 2-6 workspaces and click `Merge memory` to create a new merged workspace.

The merge uses an equal context split across selected sessions. For example, if two sessions are selected, each contributes roughly half of the merged chunk budget. The merged workspace can then be queried like a normal workspace.

Current implementation details:

- Endpoint: `POST /workspaces/merge`
- Default total merge budget: 80 chunks
- Maximum selected sessions: 6
- Source chunks keep their original document metadata and include source workspace metadata internally
- A system message is added to the merged workspace explaining which sessions were merged

## Planned Features

- ChromaDB vector database integration
- LlamaIndex RAG pipeline
- OpenAI/Gemini grounded answer generation improvements
- RAGAS faithfulness scoring
- Hallucination flagging
- Citation generation
- Source sentence highlighting
- Multi-document summarization
- Contradiction detection across papers
- arXiv search and paper import
- Authentication and user-level workspaces
- Deployment configuration

## Production Readiness

The current app includes the following hardening for production-style use:

- Pinned backend and frontend dependencies with clean `pip-audit`, `bandit`, and `npm audit` checks.
- Configurable CORS origins through `CORS_ORIGINS` and host validation through `ALLOWED_HOSTS`.
- Production mode via `APP_ENV=production`, which disables autogenerated API docs.
- Upload limits through `MAX_UPLOAD_MB`, `MAX_PDF_PAGES`, and `MAX_CHUNKS_PER_DOCUMENT`.
- PDF validation using extension/content type plus PDF file signature checks.
- Safe workspace ID validation to prevent path traversal in local storage.
- Generic server error responses with internal logging.
- Frontend-side upload validation, upload progress, backend status, and LLM/local mode display.

Before deploying publicly:

1. Set `APP_ENV=production`.
2. Set `FRONTEND_ORIGIN` and `CORS_ORIGINS` to the deployed frontend URL.
3. Set `ALLOWED_HOSTS` to the API domain, for example `api.example.com`.
4. Store `OPENAI_API_KEY` in the platform secret manager, not in source control.
5. Put the API behind HTTPS and a reverse proxy or managed app platform.
6. Add authentication before storing private or user-specific documents.
7. Move from local JSON storage to a managed database/object store for multi-user deployments.

## Best Build Order

1. PDF upload
2. Text extraction
3. Chunking
4. Embeddings
5. ChromaDB retrieval
6. Basic Q&A
7. Source display
8. Faithfulness scoring
9. Multi-agent structure
10. Summarization
11. Citations
12. arXiv import
13. Contradiction detection
14. Benchmarking
15. Deployment

## Issue Tracker Suggestions

Use GitHub Issues for project planning. Recommended labels:

- `bug`
- `feature`
- `frontend`
- `backend`
- `rag`
- `docs`
- `good first issue`
- `priority-high`

Suggested initial issues:

1. Add ChromaDB-backed persistent vector storage.
2. Add RAGAS faithfulness score to each answer.
3. Improve PDF chunking with section/page metadata.
4. Add citation generation for retrieved sources.
5. Add arXiv paper search and import.
6. Add loading states and upload progress UI.
7. Add tests for PDF extraction and query flow.

## Security Notes

- Do not commit API keys.
- Do not paste production keys into issues, commits, or chat logs.
- If a key is exposed, rotate it immediately from the provider dashboard.
- Keep `backend/.env` local to each developer.

## Useful Commands

Backend compile check:

```bash
cd backend
source .venv/bin/activate
python -m compileall app
```

Frontend build check:

```bash
cd frontend
npm run build
```

Security checks:

```bash
pip-audit -r backend/requirements.txt
bandit -r backend/app
cd frontend && npm audit --audit-level=moderate
```

## License

Academic project repository. Add a formal license before public release if needed.
