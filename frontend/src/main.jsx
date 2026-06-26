import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import axios from "axios";
import { FileUp, MessageSquareText, Plus, Send } from "lucide-react";
import "./styles.css";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
});

function App() {
  const [workspaces, setWorkspaces] = useState([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [workspaceName, setWorkspaceName] = useState("Literature Review");
  const [file, setFile] = useState(null);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const activeWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.id === workspaceId),
    [workspaceId, workspaces],
  );

  async function refreshWorkspaces() {
    const response = await api.get("/workspaces");
    setWorkspaces(response.data);
    if (!workspaceId && response.data.length > 0) {
      setWorkspaceId(response.data[0].id);
    }
  }

  useEffect(() => {
    refreshWorkspaces().catch(() => setError("Backend is not reachable yet."));
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
    setError("");
    setBusy("Creating workspace...");
    try {
      const response = await api.post("/workspaces", { name: workspaceName });
      await refreshWorkspaces();
      setWorkspaceId(response.data.id);
      setMessages([]);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not create workspace.");
    } finally {
      setBusy("");
    }
  }

  async function uploadPdf(event) {
    event.preventDefault();
    if (!workspaceId || !file) return;
    setError("");
    setBusy("Uploading and indexing PDF...");
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await api.post(`/workspaces/${workspaceId}/documents`, form);
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
      setError(err.response?.data?.detail || "Could not upload this PDF.");
    } finally {
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
        top_k: 5,
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
      setError(err.response?.data?.detail || "Could not answer that question.");
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

        <form onSubmit={createWorkspace} className="panel">
          <label htmlFor="workspace-name">Workspace</label>
          <div className="row">
            <input
              id="workspace-name"
              value={workspaceName}
              onChange={(event) => setWorkspaceName(event.target.value)}
            />
            <button type="submit" title="Create workspace">
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
            onChange={(event) => setFile(event.target.files?.[0] || null)}
          />
          <button className="wide" type="submit" disabled={!workspaceId || !file || Boolean(busy)}>
            <FileUp size={18} />
            Index paper
          </button>
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
            <span>{busy || "Ready"}</span>
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
              {message.sources && (
                <div className="sources">
                  {message.sources.map((source) => (
                    <details key={source.chunk_id}>
                      <summary>
                        {source.filename}, page {source.page} · score {source.score}
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
          <input
            value={question}
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
