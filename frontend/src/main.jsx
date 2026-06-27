import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import {
  Activity,
  BarChart3,
  BookOpenCheck,
  FileSearch,
  FileUp,
  Layers3,
  MessageSquareText,
  Plus,
  Quote,
  Radar,
  Send,
  ShieldCheck,
} from "lucide-react";
import "./styles.css";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
  timeout: 120000,
});

const defaultConfig = {
  app_env: "development",
  max_upload_mb: 25,
  max_pdf_pages: 80,
  max_chunks_per_document: 1200,
  llm_enabled: false,
};

function errorMessage(err, fallback) {
  const detail = err.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg).join(" ");
  }
  return detail || fallback;
}

function App() {
  const [workspaces, setWorkspaces] = useState([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [workspaceName, setWorkspaceName] = useState("Literature Review");
  const [mergeName, setMergeName] = useState("");
  const [selectedSessions, setSelectedSessions] = useState([]);
  const [file, setFile] = useState(null);
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);
  const [messages, setMessages] = useState([]);
  const [appConfig, setAppConfig] = useState(defaultConfig);
  const [apiStatus, setApiStatus] = useState("checking");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const activeWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.id === workspaceId),
    [workspaceId, workspaces],
  );
  const statusMode = appConfig.llm_enabled ? "LLM ready" : "Local mode";
  const dashboard = useMemo(() => {
    const sourceCount = messages.reduce((total, message) => total + (message.sources?.length || 0), 0);
    const assistantCount = messages.filter((message) => message.role === "assistant").length;
    const scores = messages.flatMap((message) => (message.sources || []).map((source) => Number(source.score)));
    const averageScore =
      scores.length > 0 ? scores.reduce((total, score) => total + score, 0) / scores.length : null;

    return {
      assistantCount,
      sourceCount,
      averageScore,
      documentCount: activeWorkspace?.document_count || 0,
    };
  }, [activeWorkspace, messages]);

  async function refreshWorkspaces() {
    const response = await api.get("/workspaces");
    setWorkspaces(response.data);
    if (!workspaceId && response.data.length > 0) {
      setWorkspaceId(response.data[0].id);
    }
  }

  function toggleSession(workspaceId) {
    setSelectedSessions((current) =>
      current.includes(workspaceId)
        ? current.filter((id) => id !== workspaceId)
        : [...current, workspaceId],
    );
  }

  useEffect(() => {
    Promise.all([
      refreshWorkspaces(),
      api.get("/config").then((response) => setAppConfig(response.data)),
      api.get("/health").then(() => setApiStatus("online")),
    ]).catch(() => {
      setApiStatus("offline");
      setError("Backend is not reachable yet.");
    });
  }, []);

  useEffect(() => {
    if (!workspaceId) {
      setMessages([]);
      return;
    }

    api
      .get(`/workspaces/${workspaceId}/messages`)
      .then((response) => setMessages(response.data))
      .catch(() => setError("Could not load this workspace conversation."));
  }, [workspaceId]);

  async function createWorkspace(event) {
    event.preventDefault();
    const name = workspaceName.trim();
    if (!name) return;
    setError("");
    setBusy("Creating workspace...");
    try {
      const response = await api.post("/workspaces", { name });
      await refreshWorkspaces();
      setWorkspaceId(response.data.id);
      setMessages([]);
    } catch (err) {
      setError(errorMessage(err, "Could not create workspace."));
    } finally {
      setBusy("");
    }
  }

  async function mergeSessions(event) {
    event.preventDefault();
    if (selectedSessions.length < 2) return;
    setError("");
    setBusy("Merging selected sessions...");
    try {
      const response = await api.post("/workspaces/merge", {
        workspace_ids: selectedSessions,
        name: mergeName.trim() || undefined,
        total_chunk_budget: 80,
      });
      await refreshWorkspaces();
      setWorkspaceId(response.data.id);
      setSelectedSessions([]);
      setMergeName("");
      setMessages([]);
    } catch (err) {
      setError(errorMessage(err, "Could not merge the selected sessions."));
    } finally {
      setBusy("");
    }
  }

  function selectPdf(event) {
    const selected = event.target.files?.[0] || null;
    setError("");
    setFile(null);
    if (!selected) return;
    if (selected.type !== "application/pdf" && !selected.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported.");
      event.target.value = "";
      return;
    }
    if (selected.size > appConfig.max_upload_mb * 1024 * 1024) {
      setError(`PDF is too large. Maximum upload size is ${appConfig.max_upload_mb} MB.`);
      event.target.value = "";
      return;
    }
    setFile(selected);
  }

  async function uploadPdf(event) {
    event.preventDefault();
    if (!workspaceId || !file) return;
    setError("");
    setUploadProgress(0);
    setBusy("Uploading and indexing PDF...");
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await api.post(`/workspaces/${workspaceId}/documents`, form, {
        onUploadProgress: (progressEvent) => {
          if (!progressEvent.total) return;
          setUploadProgress(Math.round((progressEvent.loaded * 100) / progressEvent.total));
        },
      });
      setMessages((current) => [
        ...current,
        {
          role: "system",
          text: `Indexed ${response.data.filename}: ${response.data.pages} pages, ${response.data.chunks} chunks.`,
          sources: [],
        },
      ]);
      setFile(null);
      await refreshWorkspaces();
    } catch (err) {
      setError(errorMessage(err, "Could not upload this PDF."));
    } finally {
      setUploadProgress(0);
      setBusy("");
    }
  }

  async function askQuestion(event) {
    event.preventDefault();
    if (!workspaceId || !question.trim()) return;
    const asked = question.trim();
    setQuestion("");
    setError("");
    setBusy("Thinking over your papers...");
    setMessages((current) => [...current, { role: "user", text: asked }]);
    try {
      const response = await api.post(`/workspaces/${workspaceId}/query`, {
        question: asked,
        top_k: topK,
      });
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: response.data.answer,
          sources: response.data.sources,
        },
      ]);
    } catch (err) {
      setError(errorMessage(err, "Could not answer that question."));
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div>
          <h1>RAG Research Assistant</h1>
          <p>Upload papers, ask questions, and inspect the sources behind each answer.</p>
        </div>

        <div className="status-grid">
          <div className={`status-pill ${apiStatus}`}>
            <Activity size={16} />
            {apiStatus}
          </div>
          <div className="status-pill">
            <ShieldCheck size={16} />
            {statusMode}
          </div>
        </div>

        <form onSubmit={createWorkspace} className="panel">
          <label htmlFor="workspace-name">Workspace</label>
          <div className="row">
            <input
              id="workspace-name"
              value={workspaceName}
              maxLength={80}
              onChange={(event) => setWorkspaceName(event.target.value)}
            />
            <button type="submit" title="Create workspace" disabled={Boolean(busy) || !workspaceName.trim()}>
              <Plus size={18} />
            </button>
          </div>
        </form>

        <section className="panel">
          <label htmlFor="workspace-select">Active workspace</label>
          <select
            id="workspace-select"
            value={workspaceId}
            onChange={(event) => setWorkspaceId(event.target.value)}
          >
            <option value="">Select workspace</option>
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.name} ({workspace.document_count})
              </option>
            ))}
          </select>
        </section>

        <form onSubmit={mergeSessions} className="panel session-merge">
          <div className="panel-title">
            <label>Session memory</label>
            <span>{selectedSessions.length} selected</span>
          </div>
          <div className="session-list">
            {workspaces.length === 0 && <span className="hint">Create sessions to merge their memory.</span>}
            {workspaces.map((workspace) => (
              <label className="session-item" key={workspace.id}>
                <input
                  type="checkbox"
                  checked={selectedSessions.includes(workspace.id)}
                  onChange={() => toggleSession(workspace.id)}
                />
                <span>
                  <strong>{workspace.name}</strong>
                  <small>{workspace.document_count} document(s)</small>
                </span>
              </label>
            ))}
          </div>
          <input
            value={mergeName}
            maxLength={80}
            placeholder="Merged session name"
            onChange={(event) => setMergeName(event.target.value)}
          />
          <button className="wide" type="submit" disabled={selectedSessions.length < 2 || Boolean(busy)}>
            <Layers3 size={18} />
            Merge memory
          </button>
          <span className="hint">
            Merging splits the context budget equally. With two sessions, each contributes half of the memory.
          </span>
        </form>

        <form onSubmit={uploadPdf} className="panel">
          <label htmlFor="pdf-upload">Upload PDF</label>
          <input
            id="pdf-upload"
            type="file"
            accept="application/pdf"
            onChange={selectPdf}
          />
          {file && <span className="file-meta">{file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB</span>}
          {uploadProgress > 0 && (
            <div className="progress" aria-label="Upload progress">
              <span style={{ width: `${uploadProgress}%` }} />
            </div>
          )}
          <button className="wide" type="submit" disabled={!workspaceId || !file || Boolean(busy)}>
            <FileUp size={18} />
            Index paper
          </button>
          <span className="hint">
            Max {appConfig.max_upload_mb} MB, {appConfig.max_pdf_pages} pages.
          </span>
        </form>

        {activeWorkspace && (
          <div className="workspace-note">
            <strong>{activeWorkspace.name}</strong>
            <span>{activeWorkspace.document_count} indexed document(s)</span>
          </div>
        )}
      </aside>

      <section className="chat">
        <header>
          <MessageSquareText size={22} />
          <div>
            <h2>Ask Your Papers</h2>
            <span>{busy || `${activeWorkspace?.name || "No workspace"} · ${messages.length} message${messages.length === 1 ? "" : "s"}`}</span>
          </div>
        </header>

        {error && <div className="error">{error}</div>}

        <div className="messages">
          <section className="dashboard" aria-label="Workspace dashboard">
            <div className="metric-row">
              <div className="metric">
                <FileSearch size={18} />
                <span>Documents</span>
                <strong>{dashboard.documentCount}</strong>
              </div>
              <div className="metric">
                <MessageSquareText size={18} />
                <span>Answers</span>
                <strong>{dashboard.assistantCount}</strong>
              </div>
              <div className="metric">
                <Quote size={18} />
                <span>Sources used</span>
                <strong>{dashboard.sourceCount}</strong>
              </div>
              <div className="metric">
                <BarChart3 size={18} />
                <span>Avg. score</span>
                <strong>{dashboard.averageScore === null ? "N/A" : dashboard.averageScore.toFixed(3)}</strong>
              </div>
            </div>

            <div className="insight-grid">
              <article className="insight">
                <Radar size={18} />
                <div>
                  <h3>Source Score</h3>
                  <p>
                    Higher scores mean the passage is a stronger match for your question. Use them to compare
                    evidence, not as a final truth rating.
                  </p>
                  <div className="score-scale" aria-label="Score guide">
                    <span>0.20 weak</span>
                    <span>0.50 useful</span>
                    <span>0.80 strong</span>
                  </div>
                </div>
              </article>
              <article className="insight">
                <Layers3 size={18} />
                <div>
                  <h3>RAG Flow</h3>
                  <p>
                    The app extracts PDF text, chunks it, embeds each chunk, retrieves relevant passages, then
                    answers with source snippets you can inspect.
                  </p>
                </div>
              </article>
              <article className="insight">
                <BookOpenCheck size={18} />
                <div>
                  <h3>Research Features</h3>
                  <p>
                    Upload papers, ask grounded questions, choose how many sources to retrieve, inspect pages,
                    and use summary prompts for fast literature review.
                  </p>
                </div>
              </article>
            </div>
          </section>

          {messages.length === 0 && (
            <div className="empty">
              Create a workspace, upload a PDF, then ask a question like “What is the main problem this paper solves?”
            </div>
          )}
          {messages.map((message, index) => (
            <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
              <p>{message.text}</p>
              {message.sources && (
                <div className="sources">
                  {message.sources.map((source) => (
                    <details key={source.chunk_id}>
                      <summary>
                        {source.filename}, page {source.page} · score {Number(source.score).toFixed(3)}
                      </summary>
                      <p>{source.text}</p>
                    </details>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>

        <form onSubmit={askQuestion} className="composer">
          <select
            aria-label="Number of sources"
            value={topK}
            onChange={(event) => setTopK(Number(event.target.value))}
          >
            {[3, 5, 8, 10].map((value) => (
              <option key={value} value={value}>
                {value} sources
              </option>
            ))}
          </select>
          <input
            value={question}
            maxLength={1200}
            placeholder="Ask a question about the uploaded PDFs..."
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button type="submit" disabled={!workspaceId || !question.trim() || Boolean(busy)} title="Ask question">
            <Send size={18} />
          </button>
        </form>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
