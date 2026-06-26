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
- Local fallback mode when no OpenAI key is configured

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
OPENAI_API_KEY=your_key_here
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
FRONTEND_ORIGIN=http://localhost:5173
```

The app still works without `OPENAI_API_KEY` using local fallback retrieval and extractive answers.

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
- Ask summary prompts like:

```txt
brief me about this paper
what is the paper about
summarize the main contributions
```

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

## License

Academic project repository. Add a formal license before public release if needed.
