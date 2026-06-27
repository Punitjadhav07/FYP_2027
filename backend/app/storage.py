import json
import re
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from app.config import get_settings


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or "workspace"


def validate_workspace_id(workspace_id: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,90}-[a-f0-9]{8}", workspace_id):
        raise ValueError("Invalid workspace id")
    return workspace_id


def workspace_path(workspace_id: str) -> Path:
    settings = get_settings()
    workspace_id = validate_workspace_id(workspace_id)
    root = (settings.storage_dir / "workspaces").resolve()
    path = (root / workspace_id).resolve()
    if root != path and root not in path.parents:
        raise ValueError("Invalid workspace path")
    return path


def workspace_dir(workspace_id: str) -> Path:
    path = workspace_path(workspace_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def workspace_meta_path(workspace_id: str) -> Path:
    return workspace_path(workspace_id) / "workspace.json"


def chunks_path(workspace_id: str) -> Path:
    return workspace_path(workspace_id) / "chunks.json"


def messages_path(workspace_id: str) -> Path:
    return workspace_path(workspace_id) / "messages.json"


def create_workspace(name: str) -> dict:
    workspace_id = f"{slugify(name)}-{uuid4().hex[:8]}"
    meta = {"id": workspace_id, "name": name}
    path = workspace_dir(workspace_id)
    (path / "workspace.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (path / "chunks.json").write_text("[]", encoding="utf-8")
    (path / "messages.json").write_text("[]", encoding="utf-8")
    return meta


def list_workspaces() -> list[dict]:
    root = get_settings().storage_dir / "workspaces"
    if not root.exists():
        return []

    workspaces = []
    for meta_file in sorted(root.glob("*/workspace.json")):
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        chunks = load_chunks(meta["id"])
        docs = {chunk["document_id"] for chunk in chunks}
        workspaces.append({**meta, "document_count": len(docs)})
    return workspaces


def get_workspace(workspace_id: str) -> dict | None:
    try:
        path = workspace_meta_path(workspace_id)
    except ValueError:
        return None
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_chunks(workspace_id: str) -> list[dict]:
    path = chunks_path(workspace_id)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def append_chunks(workspace_id: str, chunks: list[dict]) -> None:
    existing = load_chunks(workspace_id)
    existing.extend(chunks)
    chunks_path(workspace_id).write_text(json.dumps(existing, indent=2), encoding="utf-8")


def load_messages(workspace_id: str) -> list[dict]:
    path = messages_path(workspace_id)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def append_message(
    workspace_id: str,
    role: str,
    text: str,
    sources: list[dict] | None = None,
) -> dict:
    message = {
        "id": uuid4().hex,
        "role": role,
        "text": text,
        "sources": sources or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    messages = load_messages(workspace_id)
    messages.append(message)
    messages_path(workspace_id).write_text(json.dumps(messages, indent=2), encoding="utf-8")
    return message
