# Multi-Agent RAG Research Assistant

A web-based research assistant for uploading academic PDFs, indexing their content, and asking source-grounded questions over the uploaded papers.

This repository currently contains the MVP for:

- Workspace creation
- PDF upload and text extraction
- Local chunking and indexing
- Basic retrieval-based Q&A
- Source snippets with page references
- Dedicated source-backed summarization
- Structured citations for answers and summaries
- Per-workspace conversation history saved locally
- Separate dark dashboard page with workspace metrics, score education, session merge, and API policy controls
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
CHUNK_MAX_WORDS=180
CHUNK_OVERLAP_WORDS=35
DEFAULT_QUERY_SOURCES=5
DEFAULT_SUMMARY_SOURCES=8
DEFAULT_MERGE_CHUNK_BUDGET=80
GOOGLE_CLIENT_ID=
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
- Navigate between the chat page and a separate dashboard page
- View document count, answer count, source count, average retrieval score, and score guidance
- Generate a dedicated workspace summary with optional focus text
- View structured citations for generated answers and summaries
- Select multiple sessions and merge their memory into a new workspace using backend-controlled token policy
- Ask summary prompts or use the dedicated summary button:

```txt
brief me about this paper
what is the paper about
summarize the main contributions
```

## Summaries and Citations

Use the `Summarization` panel in the sidebar to generate a dedicated summary for the active workspace. The optional focus field can steer the summary toward a topic such as methods, limitations, datasets, or contributions.

The backend endpoint is:

```txt
POST /workspaces/{workspace_id}/summarize
```

Answers and summaries return two evidence layers:

- `citations`: compact citation records labeled `[S1]`, `[S2]`, etc. with filename, page, chunk ID, and retrieval score.
- `sources`: expandable text snippets used as the retrieval evidence.

Citation format in the UI:

```txt
[S1] paper-name.pdf, p. 3 (retrieval score 0.742)
```

## API Usage Policy

Users should not control token budgets directly. The backend owns API usage limits so the team can control cost and avoid accidental token exhaustion.

Tune these values in `backend/.env`:

- `DEFAULT_QUERY_SOURCES`: evidence chunks used per answer.
- `DEFAULT_SUMMARY_SOURCES`: evidence chunks used per summary.
- `DEFAULT_MERGE_CHUNK_BUDGET`: total chunks copied into a merged workspace.
- `CHUNK_MAX_WORDS`: target chunk size during PDF indexing.
- `CHUNK_OVERLAP_WORDS`: overlap between chunks.
- `MAX_CHUNKS_PER_DOCUMENT`: hard cap for each uploaded document.

The dashboard displays these policies to users, but does not let users change them.

## Session Memory Merge

The dashboard includes a `Merge Session Memory` panel. Select 2-6 workspaces and click `Merge selected memory` to create a new merged workspace.

The merge uses an equal context split across selected sessions. For example, if two sessions are selected, each contributes roughly half of the merged chunk budget. The merged workspace can then be queried like a normal workspace.

Current implementation details:

- Endpoint: `POST /workspaces/merge`
- Default total merge budget: 80 chunks
- Maximum selected sessions: 6
- Source chunks keep their original document metadata and include source workspace metadata internally
- A system message is added to the merged workspace explaining which sessions were merged

## User Management

The app includes local email/password signup and login so demos can show multiple users with isolated papers, sessions, summaries, and merged workspaces. Every new signup receives a fresh `Literature Review` workspace owned by that user. Workspaces without the signed-in user's `owner_id` are not listed and cannot be opened through the API.

Authenticated requests use a bearer token returned by:

- `POST /auth/signup`
- `POST /auth/login`
- `GET /auth/me`

This local auth is intended for project demos and internal testing. Passwords are salted and hashed, but sessions are stored in local JSON and do not yet include expiry, revocation, email verification, password reset, rate limiting, or HTTPS-only cookie handling.

Google sign-in is still planned as the production user-management upgrade. Add this value when the Google OAuth app is ready:

```env
GOOGLE_CLIENT_ID=your_google_oauth_web_client_id
```

The app exposes whether Google is configured through `/config`. Without `GOOGLE_CLIENT_ID`, the frontend uses the local email/password flow.

## Implementation Status

This section reflects the current codebase state after reviewing `backend/app`, `frontend/src`, dependencies, and the README feature list.

### Implemented

- Local email/password signup, login, bearer-token auth, and per-user workspace isolation.
- Workspace creation, listing, stats, message history, and active workspace selection.
- PDF upload with file type checks, PDF signature validation, upload size limits, page limits, and chunk caps.
- PDF text extraction with PyMuPDF.
- Configurable chunking through `CHUNK_MAX_WORDS` and `CHUNK_OVERLAP_WORDS`.
- OpenAI embeddings when API quota is available.
- Local deterministic embedding fallback when OpenAI is unavailable, invalid, or out of quota.
- Local JSON storage for users, sessions, workspaces, chunks, uploads, and messages.
- Basic RAG retrieval with semantic score plus keyword/summary heuristics.
- Basic Q&A over uploaded PDFs.
- Evidence sources with filename, page, chunk ID, retrieval score, and expandable source text.
- Structured citation records labeled `[S1]`, `[S2]`, etc. for answers and summaries.
- Dedicated workspace summarization endpoint and UI action.
- Summary focus field for steering summaries toward methods, limitations, datasets, contributions, or another topic.
- Dark themed frontend.
- Separate dashboard view with workspace metrics, evidence-match education, API policy display, feature controls, and merge controls.
- Session memory merge across 2-6 user-owned workspaces.
- Backend-controlled merge budget through `DEFAULT_MERGE_CHUNK_BUDGET`.
- Backend-controlled answer and summary evidence budgets through `DEFAULT_QUERY_SOURCES` and `DEFAULT_SUMMARY_SOURCES`.
- Current-date guardrail for questions that should not be answered from stale PDF context.
- Basic author extraction fallback for author-style questions.
- Production-oriented configuration for CORS, trusted hosts, upload limits, and disabled docs in production mode.
- GitHub issue and pull request templates.

### Partially Implemented

- Multi-document summarization: summaries can use retrieved chunks across a workspace, but there is no advanced document-level synthesis planner yet.
- Citations: answers include source labels and page references, but the app does not yet generate formal bibliography formats such as APA, IEEE, or BibTeX.
- Faithfulness support: retrieval scores and evidence snippets help users inspect grounding, but there is no RAGAS or LLM-judge faithfulness score yet.
- Hallucination handling: the prompt asks the model to answer from context and the backend refuses low-evidence questions, but there is no dedicated hallucination classifier or flagging workflow.
- Multi-agent structure: the app has orchestration-like feature separation, but not a real multi-agent architecture with specialist agents, handoffs, or evaluator agents.
- Production readiness: security/config hardening exists, but storage, auth, deployment, observability, and tests are still not production-grade.
- User management: local auth works for demos, but Google OAuth and production session management are not implemented.
- Session memory merge: merge works by copying an equal chunk budget from each selected workspace, but it is not yet token-aware summarization/compression of each session's memory.

### Not Implemented Yet

- ChromaDB persistent vector database.
- LlamaIndex pipeline.
- Gemini provider support.
- RAGAS faithfulness scoring.
- LLM-judge or classifier-based hallucination flagging.
- Source sentence highlighting inside PDF/page text.
- arXiv search and paper import.
- Contradiction detection across papers.
- Benchmarking/evaluation suite.
- Automated backend tests.
- Automated frontend tests.
- CI workflow for lint/build/test/security checks.
- Dockerfile and Docker Compose setup.
- Deployment manifests or hosting-specific configuration.
- Managed database and object storage.
- Session expiry, logout token revocation, refresh tokens, rate limiting, email verification, password reset, and HTTPS-only cookie auth.
- Google OAuth sign-in.
- Formal citation export formats.
- Workspace/document deletion and document re-indexing controls.

## Remaining Work

### Priority 1: Stabilize The Current MVP

1. Add automated backend tests for auth, workspace isolation, PDF upload, query, summarization, citations, and merge.
2. Add frontend smoke tests for signup/login, upload, chat, dashboard, summary, and merge flows.
3. Add a CI workflow that runs `python -m compileall`, backend tests, `npm run build`, `pip-audit`, `bandit`, and `npm audit`.
4. Add workspace and document delete controls so demo data can be cleaned safely.
5. Add clearer empty/error states for quota fallback, no evidence found, and empty merged workspaces.

### Priority 2: Upgrade Retrieval Quality

1. Replace local JSON chunk storage with ChromaDB.
2. Store embedding metadata in ChromaDB with workspace, owner, document, filename, page, and chunk IDs.
3. Add document-level metadata extraction such as title, authors, abstract, year, and section headings.
4. Improve chunking with section-aware splitting instead of only word windows.
5. Add re-indexing when chunking or embedding settings change.

### Priority 3: Add Real Evaluation And Trust Features

1. Add RAGAS faithfulness scoring for each answer.
2. Add answer relevancy and context precision/recall metrics.
3. Add hallucination flagging when generated claims are not supported by retrieved passages.
4. Add source sentence highlighting so users can see the exact supporting sentence.
5. Add contradiction detection across selected papers or workspaces.

### Priority 4: Expand Research Workflow

1. Add arXiv search and import by URL, paper ID, title, or keyword.
2. Add formal citation exports such as APA, IEEE, BibTeX, and RIS.
3. Add multi-document literature review synthesis with themes, gaps, methods, datasets, and limitations.
4. Add comparison views for papers, claims, methods, datasets, and findings.
5. Add saved notes or annotations per source snippet.

### Priority 5: Production Deployment

1. Replace local JSON users/sessions/storage with a managed database and object storage.
2. Replace local demo auth with Google OAuth or a managed identity provider.
3. Add session expiry, token revocation, refresh handling, and rate limiting.
4. Add Dockerfile and Docker Compose.
5. Add deployment configuration for the selected hosting platform.
6. Add structured logging, request IDs, and basic monitoring.
7. Add backup and migration strategy for workspace/document data.

## Planned Features

- ChromaDB vector database integration
- LlamaIndex RAG pipeline
- OpenAI/Gemini grounded answer generation improvements
- RAGAS faithfulness scoring
- Hallucination flagging
- Source sentence highlighting
- Multi-document summarization
- Contradiction detection across papers
- arXiv search and paper import
- Google OAuth and production session management
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
6. Replace demo local auth with OAuth or managed identity before storing real private documents.
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
