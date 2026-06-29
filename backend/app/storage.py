import json
import re
import secrets
import hashlib
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


def users_path() -> Path:
    return get_settings().storage_dir / "users.json"


def sessions_path() -> Path:
    return get_settings().storage_dir / "sessions.json"


def workspace_meta_path(workspace_id: str) -> Path:
    return workspace_path(workspace_id) / "workspace.json"


def chunks_path(workspace_id: str) -> Path:
    return workspace_path(workspace_id) / "chunks.json"


def messages_path(workspace_id: str) -> Path:
    return workspace_path(workspace_id) / "messages.json"


def create_workspace(name: str, owner_id: str) -> dict:
    workspace_id = f"{slugify(name)}-{uuid4().hex[:8]}"
    meta = {"id": workspace_id, "name": name, "owner_id": owner_id}
    path = workspace_dir(workspace_id)
    (path / "workspace.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (path / "chunks.json").write_text("[]", encoding="utf-8")
    (path / "messages.json").write_text("[]", encoding="utf-8")
    return meta


def list_workspaces(owner_id: str | None = None) -> list[dict]:
    root = get_settings().storage_dir / "workspaces"
    if not root.exists():
        return []

    workspaces = []
    for meta_file in sorted(root.glob("*/workspace.json")):
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if owner_id and meta.get("owner_id") != owner_id:
            continue
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


def get_user_workspace(workspace_id: str, owner_id: str) -> dict | None:
    workspace = get_workspace(workspace_id)
    if not workspace or workspace.get("owner_id") != owner_id:
        return None
    return workspace


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
    citations: list[dict] | None = None,
) -> dict:
    message = {
        "id": uuid4().hex,
        "role": role,
        "text": text,
        "sources": sources or [],
        "citations": citations or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    messages = load_messages(workspace_id)
    messages.append(message)
    messages_path(workspace_id).write_text(json.dumps(messages, indent=2), encoding="utf-8")
    return message


def load_users() -> list[dict]:
    path = users_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_users(users: list[dict]) -> None:
    users_path().write_text(json.dumps(users, indent=2), encoding="utf-8")


def load_sessions() -> dict:
    path = sessions_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_sessions(sessions: dict) -> None:
    sessions_path().write_text(json.dumps(sessions, indent=2), encoding="utf-8")


def password_hash(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return salt, digest.hex()


def create_user(email: str, password: str, name: str | None = None) -> dict:
    users = load_users()
    if any(user["email"] == email for user in users):
        raise ValueError("Email already registered")
    salt, hashed = password_hash(password)
    user = {
        "id": uuid4().hex,
        "email": email,
        "name": name or email.split("@", 1)[0],
        "password_salt": salt,
        "password_hash": hashed,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    users.append(user)
    save_users(users)
    return user


def authenticate_user(email: str, password: str) -> dict | None:
    for user in load_users():
        salt, hashed = password_hash(password, user["password_salt"])
        if user["email"] == email and secrets.compare_digest(user["password_hash"], hashed):
            return user
    return None


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    sessions = load_sessions()
    sessions[token] = {"user_id": user_id, "created_at": datetime.now(timezone.utc).isoformat()}
    save_sessions(sessions)
    return token


def get_session_user(token: str) -> dict | None:
    session = load_sessions().get(token)
    if not session:
        return None
    for user in load_users():
        if user["id"] == session["user_id"]:
            return user
    return None


def public_user(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"], "name": user["name"]}
