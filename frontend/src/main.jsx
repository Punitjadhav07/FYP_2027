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
  default_query_sources: 5,
  default_summary_sources: 8,
  default_merge_chunk_budget: 80,
  google_enabled: false,
  llm_enabled: false,
};

function errorMessage(err, fallback) {
  const detail = err.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg).join(" ");
  }
  return detail || fallback;
}

function matchStrength(score) {
  const value = Number(score);
  if (Number.isNaN(value)) return "Unknown match";
  if (value >= 0.75 || value >= 4) return "Strong match";
  if (value >= 0.45 || value >= 2) return "Good match";
  return "Possible match";
}

function App() {
  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState({ email: "", password: "", name: "" });
  const [authToken, setAuthToken] = useState(() => localStorage.getItem("rag_auth_token") || "");
  const [currentUser, setCurrentUser] = useState(() => {
    const saved = localStorage.getItem("rag_auth_user");
    return saved ? JSON.parse(saved) : null;
  });
  const [view, setView] = useState("chat");
  const [workspaces, setWorkspaces] = useState([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [workspaceName, setWorkspaceName] = useState("Literature Review");
  const [mergeName, setMergeName] = useState("");
  const [selectedSessions, setSelectedSessions] = useState([]);
  const [workspaceStats, setWorkspaceStats] = useState([]);
  const [file, setFile] = useState(null);
  const [question, setQuestion] = useState("");
  const [summaryFocus, setSummaryFocus] = useState("");
  const [messages, setMessages] = useState([]);
  const [appConfig, setAppConfig] = useState(defaultConfig);
  const [apiStatus, setApiStatus] = useState("checking");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.defaults.headers.common.Authorization = authToken ? `Bearer ${authToken}` : "";
  }, [authToken]);

  const activeWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.id === workspaceId),
    [workspaceId, workspaces],
  );
  const statusMode = appConfig.llm_enabled ? "LLM ready" : "Local mode";
  const selectedStats = useMemo(
    () => workspaceStats.filter((workspace) => selectedSessions.includes(workspace.id)),
    [selectedSessions, workspaceStats],
  );
  const mergePlan = useMemo(() => {
    const selectedChunks = selectedStats.reduce((total, workspace) => total + workspace.chunk_count, 0);
    const selectedTokens = selectedStats.reduce((total, workspace) => total + workspace.approx_tokens, 0);
    const perSessionBudget =
      selectedStats.length > 0 ? Math.floor(appConfig.default_merge_chunk_budget / selectedStats.length) : 0;
    const usedChunks = selectedStats.reduce(
      (total, workspace) => total + Math.min(workspace.chunk_count, perSessionBudget),
      0,
    );
    const averageTokensPerChunk = selectedChunks > 0 ? selectedTokens / selectedChunks : 0;
    const includedTokens = Math.round(usedChunks * averageTokensPerChunk);
    const remainingChunks = Math.max(0, appConfig.default_merge_chunk_budget - usedChunks);
    return {
      perSessionBudget,
      selectedChunks,
      selectedTokens,
      includedTokens,
      usedChunks,
      remainingChunks,
      remainingTokens: Math.round(remainingChunks * averageTokensPerChunk),
    };
  }, [appConfig.default_merge_chunk_budget, selectedStats]);
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
    const [workspaceResponse, statsResponse] = await Promise.all([
      api.get("/workspaces"),
      api.get("/workspaces/stats"),
    ]);
    setWorkspaces(workspaceResponse.data);
    setWorkspaceStats(statsResponse.data);
    if (!workspaceId && workspaceResponse.data.length > 0) {
      setWorkspaceId(workspaceResponse.data[0].id);
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
    if (!authToken) return;
    Promise.all([
      refreshWorkspaces(),
      api.get("/config").then((response) => setAppConfig(response.data)),
      api.get("/health").then(() => setApiStatus("online")),
    ]).catch(() => {
      setApiStatus("offline");
      setError("Backend is not reachable yet.");
    });
  }, [authToken]);

  useEffect(() => {
    if (!authToken || !workspaceId) {
      setMessages([]);
      return;
    }

    api
      .get(`/workspaces/${workspaceId}/messages`)
      .then((response) => setMessages(response.data))
      .catch(() => setError("Could not load this workspace conversation."));
  }, [authToken, workspaceId]);

  async function submitAuth(event) {
    event.preventDefault();
    setError("");
    setBusy(authMode === "login" ? "Signing in..." : "Creating account...");
    try {
      const response = await api.post(`/auth/${authMode}`, authForm);
      setAuthToken(response.data.token);
      setCurrentUser(response.data.user);
      localStorage.setItem("rag_auth_token", response.data.token);
      localStorage.setItem("rag_auth_user", JSON.stringify(response.data.user));
      setAuthForm({ email: "", password: "", name: "" });
    } catch (err) {
      setError(errorMessage(err, authMode === "login" ? "Could not sign in." : "Could not create account."));
    } finally {
      setBusy("");
    }
  }

  function logout() {
    setAuthToken("");
    setCurrentUser(null);
    setWorkspaces([]);
    setWorkspaceStats([]);
    setWorkspaceId("");
    setMessages([]);
    localStorage.removeItem("rag_auth_token");
    localStorage.removeItem("rag_auth_user");
  }

  if (!authToken || !currentUser) {
    return (
      <main className="auth-shell">
        <section className="auth-card">
          <div>
            <h1>RAG Research Assistant</h1>
            <p>Sign in to keep each user&apos;s papers, sessions, summaries, and merged memory separate.</p>
          </div>
          {error && <div className="error auth-error">{error}</div>}
          <form onSubmit={submitAuth} className="auth-form">
            {authMode === "signup" && (
              <input
                value={authForm.name}
                placeholder="Name"
                onChange={(event) => setAuthForm((current) => ({ ...current, name: event.target.value }))}
              />
            )}
            <input
              type="email"
              value={authForm.email}
              placeholder="Email"
              onChange={(event) => setAuthForm((current) => ({ ...current, email: event.target.value }))}
            />
            <input
              type="password"
              value={authForm.password}
              placeholder="Password"
              onChange={(event) => setAuthForm((current) => ({ ...current, password: event.target.value }))}
            />
            <button type="submit" disabled={Boolean(busy) || !authForm.email || !authForm.password}>
              {authMode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>
          <button
            className="ghost-button"
            type="button"
            onClick={() => {
              setError("");
              setAuthMode(authMode === "login" ? "signup" : "login");
            }}
          >
            {authMode === "login" ? "Need an account? Sign up" : "Already have an account? Sign in"}
          </button>
        </section>
      </main>
    );
  }

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
        top_k: appConfig.default_query_sources,
      });
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: response.data.answer,
          sources: response.data.sources,
          citations: response.data.citations,
        },
      ]);
    } catch (err) {
      setError(errorMessage(err, "Could not answer that question."));
    } finally {
      setBusy("");
    }
  }

  async function summarizeWorkspace(event) {
    event.preventDefault();
    if (!workspaceId) return;
    setError("");
    setBusy("Summarizing workspace...");
    const focus = summaryFocus.trim();
    const prompt = focus ? `Summarize this workspace focusing on: ${focus}` : "Summarize this workspace";
    setMessages((current) => [...current, { role: "user", text: prompt, sources: [], citations: [] }]);
    try {
      const response = await api.post(`/workspaces/${workspaceId}/summarize`, {
        focus: focus || undefined,
        top_k: appConfig.default_summary_sources,
      });
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: response.data.summary,
          sources: response.data.sources,
          citations: response.data.citations,
        },
      ]);
      setSummaryFocus("");
    } catch (err) {
      setError(errorMessage(err, "Could not summarize this workspace."));
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
        <div className="user-panel">
          <span>{currentUser.name}</span>
          <small>{currentUser.email}</small>
          <button type="button" onClick={logout}>Sign out</button>
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

        <nav className="nav-tabs" aria-label="Main navigation">
          <button
            type="button"
            className={view === "chat" ? "active" : ""}
            onClick={() => setView("chat")}
          >
            <MessageSquareText size={17} />
            Chat
          </button>
          <button
            type="button"
            className={view === "dashboard" ? "active" : ""}
            onClick={() => setView("dashboard")}
          >
            <BarChart3 size={17} />
            Dashboard
          </button>
        </nav>

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

        <form onSubmit={summarizeWorkspace} className="panel">
          <label htmlFor="summary-focus">Summarization</label>
          <input
            id="summary-focus"
            value={summaryFocus}
            maxLength={240}
            placeholder="Optional focus, e.g. methods"
            onChange={(event) => setSummaryFocus(event.target.value)}
          />
          <button className="wide" type="submit" disabled={!workspaceId || Boolean(busy)}>
            <BookOpenCheck size={18} />
            Generate summary
          </button>
          <span className="hint">Creates a summary and lists the pages used as evidence.</span>
        </form>

        {activeWorkspace && (
          <div className="workspace-note">
            <strong>{activeWorkspace.name}</strong>
            <span>{activeWorkspace.document_count} indexed document(s)</span>
          </div>
        )}
      </aside>

      {view === "dashboard" && (
        <section className="chat dashboard-view">
          <header>
            <BarChart3 size={22} />
            <div>
              <h2>Workspace Dashboard</h2>
              <span>{busy || `${activeWorkspace?.name || "No workspace selected"} · user-owned sessions only`}</span>
            </div>
          </header>

          {error && <div className="error">{error}</div>}

          <div className="messages dashboard-messages">
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
                  <span>Avg. match</span>
                  <strong>{dashboard.averageScore === null ? "N/A" : dashboard.averageScore.toFixed(3)}</strong>
                </div>
              </div>

              <div className="insight-grid">
                <article className="control-panel memory-control">
                  <div className="control-heading">
                    <Layers3 size={18} />
                    <div>
                      <h3>Merge Session Memory</h3>
                      <p>Select from your own workspaces. The backend applies the team memory policy automatically.</p>
                    </div>
                  </div>
                  <form onSubmit={mergeSessions} className="merge-dashboard-form">
                    <div className="session-control-list">
                      {workspaceStats.length === 0 && <span className="hint">Create sessions to merge memory.</span>}
                      {workspaceStats.map((workspace) => (
                        <label className="session-control-item" key={workspace.id}>
                          <input
                            type="checkbox"
                            checked={selectedSessions.includes(workspace.id)}
                            onChange={() => toggleSession(workspace.id)}
                          />
                          <span>
                            <strong>{workspace.name}</strong>
                            <small>
                              {workspace.document_count} docs · {workspace.chunk_count} chunks · ~
                              {workspace.approx_tokens.toLocaleString()} tokens
                            </small>
                          </span>
                        </label>
                      ))}
                    </div>
                    <input
                      value={mergeName}
                      maxLength={80}
                      placeholder="Merged workspace name"
                      onChange={(event) => setMergeName(event.target.value)}
                    />
                    <div className="memory-stats">
                      <span>{selectedSessions.length} selected</span>
                      <span>{mergePlan.perSessionBudget} chunks each</span>
                      <span>~{mergePlan.includedTokens.toLocaleString()} tokens included</span>
                      <span>{appConfig.default_merge_chunk_budget} chunk team budget</span>
                    </div>
                    <div className="policy-note">
                      Users choose which sessions to combine. The backend controls how much memory each merge can use.
                    </div>
                    <button type="submit" disabled={selectedSessions.length < 2 || Boolean(busy)}>
                      <Layers3 size={18} />
                      Merge selected memory
                    </button>
                  </form>
                </article>
                <article className="control-panel">
                  <div className="control-heading">
                    <ShieldCheck size={18} />
                    <div>
                      <h3>API Usage Policy</h3>
                      <p>These limits are team-controlled so users cannot accidentally burn API tokens.</p>
                    </div>
                  </div>
                  <div className="feature-control-row">
                    <span>Sources per answer</span>
                    <strong>{appConfig.default_query_sources}</strong>
                  </div>
                  <div className="feature-control-row">
                    <span>Summary evidence pages</span>
                    <strong>{appConfig.default_summary_sources}</strong>
                  </div>
                  <div className="feature-control-row">
                    <span>Google login</span>
                    <strong>{appConfig.google_enabled ? "Ready" : "Needs keys"}</strong>
                  </div>
                </article>
                <article className="control-panel">
                  <div className="control-heading">
                    <BookOpenCheck size={18} />
                    <div>
                      <h3>Feature Controls</h3>
                      <p>Run workspace-level actions without cluttering the conversation.</p>
                    </div>
                  </div>
                  <button type="button" disabled={!workspaceId || Boolean(busy)} onClick={summarizeWorkspace}>
                    <BookOpenCheck size={18} />
                    Summarize active workspace
                  </button>
                  <p className="hint">The summary uses the current workspace and lists the evidence pages.</p>
                </article>
              </div>

              <div className="insight-grid compact-info">
                <article className="insight">
                  <Radar size={18} />
                  <div>
                    <h3>Evidence Match</h3>
                    <p>
                      Match strength tells you how closely a paper passage matched your question. It helps you decide
                      which evidence to inspect first; it is not a truth score.
                    </p>
                    <div className="score-scale" aria-label="Score guide">
                      <span>Possible</span>
                      <span>Good</span>
                      <span>Strong</span>
                    </div>
                  </div>
                </article>
                <article className="insight">
                  <Layers3 size={18} />
                  <div>
                    <h3>RAG Flow</h3>
                    <p>
                      The app reads your PDFs, finds relevant passages, and answers using those passages as evidence.
                    </p>
                  </div>
                </article>
                <article className="insight">
                  <BookOpenCheck size={18} />
                  <div>
                    <h3>User Isolation</h3>
                    <p>
                      Every signed-in user has separate workspaces, uploads, messages, summaries, and merge selections.
                    </p>
                  </div>
                </article>
              </div>
            </section>
          </div>
        </section>
      )}

      {view === "chat" && (
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
          {messages.length === 0 && (
            <div className="empty">
              Create a workspace, upload a PDF, then ask a question like “What is the main problem this paper solves?”
            </div>
          )}
          {messages.map((message, index) => (
            <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
              <p>{message.text}</p>
              {message.citations && message.citations.length > 0 && (
                <div className="evidence">
                  <div className="evidence-header">
                    <strong>Evidence used</strong>
                    <span>{message.citations.length} page reference(s)</span>
                  </div>
                  <ol className="citation-list">
                    {message.citations.map((citation) => (
                      <li key={`${citation.label}-${citation.chunk_id}`}>
                        <span>[{citation.label}]</span>
                        <div>
                          <strong>{citation.filename}</strong>
                          <small>
                            Page {citation.page} · {matchStrength(citation.score)}
                          </small>
                        </div>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              {message.sources && message.sources.length > 0 && (
                <div className="sources">
                  <strong>Exact text from papers</strong>
                  {message.sources.map((source) => (
                    <details key={source.chunk_id}>
                      <summary>{source.filename}, page {source.page}</summary>
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
            value={appConfig.default_query_sources}
            disabled
          >
            <option value={appConfig.default_query_sources}>{appConfig.default_query_sources} sources</option>
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
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
