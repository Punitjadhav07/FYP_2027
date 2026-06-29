from functools import lru_cache
from pathlib import Path
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_chat_model: str = Field(default="gpt-4o-mini", alias="OPENAI_CHAT_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL"
    )
    frontend_origin: str = Field(default="http://localhost:5173", alias="FRONTEND_ORIGIN")
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")
    allowed_hosts: str = Field(default="*", alias="ALLOWED_HOSTS")
    max_upload_mb: int = Field(default=25, ge=1, le=100, alias="MAX_UPLOAD_MB")
    max_pdf_pages: int = Field(default=80, ge=1, le=500, alias="MAX_PDF_PAGES")
    max_chunks_per_document: int = Field(default=1200, ge=1, le=10000, alias="MAX_CHUNKS_PER_DOCUMENT")
    chunk_max_words: int = Field(default=180, ge=80, le=400, alias="CHUNK_MAX_WORDS")
    chunk_overlap_words: int = Field(default=35, ge=10, le=120, alias="CHUNK_OVERLAP_WORDS")
    default_query_sources: int = Field(default=5, ge=3, le=10, alias="DEFAULT_QUERY_SOURCES")
    default_summary_sources: int = Field(default=8, ge=4, le=12, alias="DEFAULT_SUMMARY_SOURCES")
    default_merge_chunk_budget: int = Field(default=80, ge=10, le=300, alias="DEFAULT_MERGE_CHUNK_BUDGET")
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    storage_dir: Path = Field(
        default=Path(__file__).resolve().parents[1] / "storage",
        alias="STORAGE_DIR",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @computed_field
    @property
    def upload_limit_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @computed_field
    @property
    def allowed_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        if self.frontend_origin:
            origins.append(self.frontend_origin)
        if self.app_env != "production":
            origins.extend(["http://localhost:5173", "http://127.0.0.1:5173"])
        return sorted(set(origins))

    @computed_field
    @property
    def trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    return settings
