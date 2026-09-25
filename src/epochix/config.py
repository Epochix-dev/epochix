from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EPOCHIX_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    db: str = Field(
        default_factory=lambda: str(Path.home() / ".epochix" / "runs.db"),
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

    # Hosted mode (Redis pub/sub + Postgres store) is planned, not built.
    # These were documented as working and read by nothing: a run pointed at
    # Postgres silently went to the local SQLite file. Setting either is now
    # refused (see _refuse_unbuilt_backends) rather than ignored.
    redis_url: str = ""
    postgres_dsn: str = ""

    # Security
    auth_token: str = ""
    # Redact secret-looking strings from stored raw lines and from lines sent
    # to an LLM provider (epochix/scrub.py). Documented for a long time and
    # implemented nowhere; on by default now, since it only touches copies.
    scrub_secrets: bool = True
    # Comma-separated allowed CORS origins. Default empty = same-origin only
    # (browsers' SOP keeps drive-by pages from reading /api). Set to specific
    # origins (e.g. "https://app.example.com") for hosted deploys; the explicit
    # wildcard "*" stays available for opt-in open APIs.
    cors_origins: str = ""
    # Expose Swagger UI / OpenAPI schema. Off by default to avoid revealing the
    # full endpoint surface to unauthenticated visitors; can be turned on
    # explicitly, and is auto-enabled when an auth_token is configured.
    expose_docs: bool = False

    # epochix has no telemetry. Kept so existing configs that set it still
    # load; it enables nothing.
    telemetry: bool = False

    # Behaviour
    open_browser: bool = True
    keep_raw_lines: bool = False

    @model_validator(mode="after")
    def _refuse_unbuilt_backends(self) -> Settings:
        for name, value in (
            ("EPOCHIX_POSTGRES_DSN", self.postgres_dsn),
            ("EPOCHIX_REDIS_URL", self.redis_url),
        ):
            if value:
                raise ValueError(
                    f"{name} is set, but epochix has no hosted backend yet: runs would "
                    f"be written to the local SQLite file ({self.db}) instead. Unset "
                    f"{name}; see docs/config.md."
                )
        return self


def get_settings() -> Settings:
    return Settings()
