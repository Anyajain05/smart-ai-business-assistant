from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Smart AI Business Assistant"
    app_secret: str = "change-me-before-production"
    database_url: str = "data/app.db"
    upload_dir: str = "uploads"
    chroma_path: str = "data/chroma"
    access_token_minutes: int = 480
    allow_demo_bootstrap: bool = True
    huggingface_api_key: str | None = None
    huggingface_model: str | None = None
    force_llm: bool = False
    redis_url: str | None = None
    rag_cache_ttl_seconds: int = 120
    webhook_timeout_seconds: float = 10.0
    openai_api_key: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def database_path(self) -> Path:
        return Path(self.database_url)

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)

    @property
    def chroma_dir(self) -> Path:
        return Path(self.chroma_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
