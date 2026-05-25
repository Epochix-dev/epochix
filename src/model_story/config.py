from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MODEL_STORY_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    db: str = Field(
        default_factory=lambda: str(Path.home() / ".model-story" / "runs.db"),
        description="SQLite DB path. Use :memory: for tests.",
    )
    host: str = "127.0.0.1"
    port: int = 7860
    log_level: str = "INFO"

    # LLM fallback (opt-in)
    llm_enabled: bool = False
    llm_provider: Literal["ollama", "openai", "anthropic"] = "ollama"
    llm_model: str = "qwen2.5:7b"
    llm_key: str = ""
    ollama_url: str = "http://127.0.0.1:11434"

    # Phase 5 (hosted)
    redis_url: str = ""
    postgres_dsn: str = ""

    # Security
    auth_token: str = ""
    scrub_secrets: bool = False

    # Telemetry — always off by default
    telemetry: bool = False

    # Behaviour
    open_browser: bool = True
    keep_raw_lines: bool = False


def get_settings() -> Settings:
    return Settings()
