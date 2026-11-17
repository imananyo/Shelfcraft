"""Application settings loaded from environment variables / backend/.env.

Secrets (provider API keys) live only here or in the DB and are never serialized to clients.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_prefix="SHELFCRAFT_", extra="ignore"
    )

    env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    frontend_origin: str = "http://localhost:3000"
    # When set, every /api request must carry header `X-Shelfcraft-Token`.
    access_token: str | None = None

    data_dir: Path = PROJECT_DIR / "data"
    database_url: str | None = None  # default: sqlite file inside data_dir

    max_upload_mb: int = 25
    job_workers: int = 2  # total worker threads
    heavy_job_slots: int = 1  # concurrent image/video jobs (CPU bound)
    job_max_attempts: int = 3
    max_jobs_per_batch: int = 200  # Factory guard: never enqueue unlimited work
    ffmpeg_dir: str | None = None  # optional folder containing ffmpeg.exe / ffprobe.exe

    # Provider credentials — optional; providers stay disabled without them.
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    nano_banana_api_key: str | None = Field(default=None, validation_alias="NANO_BANANA_API_KEY")
    groq_api_key: str | None = Field(default=None, validation_alias="GROQ_API_KEY")
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    mistral_api_key: str | None = Field(default=None, validation_alias="MISTRAL_API_KEY")
    cloudflare_account_id: str | None = Field(default=None, validation_alias="CLOUDFLARE_ACCOUNT_ID")
    cloudflare_api_token: str | None = Field(default=None, validation_alias="CLOUDFLARE_API_TOKEN")
    ollama_base_url: str = Field(default="http://127.0.0.1:11434", validation_alias="OLLAMA_BASE_URL")

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'shelfcraft.db').as_posix()}"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.media_dir, self.models_dir, self.backups_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
