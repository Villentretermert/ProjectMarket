"""Environment configuration with optional storage for foundation smoke tests."""

from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, PostgresDsn, PrivateAttr, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    _database_pools: object | None = PrivateAttr(default=None)
    model_config = SettingsConfigDict(
        env_prefix="MARKETOB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_directory: Path | None = None
    api_workers: int = Field(default=1, ge=1, le=2)
    database_url: SecretStr | None = None
    database_timeout_seconds: int = Field(default=3, ge=2, le=30)
    database_schema: str = Field(default="public", pattern=r"^[a-z][a-z0-9_]{0,62}$")
    allowed_origins: list[str] = ["http://127.0.0.1:8000", "http://localhost:8000"]
    session_hours: int = Field(default=24, ge=1, le=24)
    bot_read_rate_limit: int = Field(default=60, ge=1, le=10000)
    bot_action_rate_limit: int = Field(default=600, ge=1, le=10000)
    action_rate_limit: int = Field(default=30, ge=1, le=10000)
    ingest_bot_per_minute: int = Field(default=60, ge=1, le=100000)
    ingest_total_per_minute: int = Field(default=1000, ge=1, le=1000000)
    auth_rate_limit: int = Field(default=10, ge=1, le=1000)
    read_rate_limit: int = Field(default=120, ge=1, le=10000)
    write_rate_limit: int = Field(default=60, ge=1, le=10000)

    @model_validator(mode="after")
    def validate_process_logging(self) -> Self:
        # Native rotating files have one writer; Docker bounds the shared stdout stream.
        if self.api_workers > 1 and self.log_directory is not None:
            raise ValueError("Multiple API workers require stdout logging (for example Docker).")
        return self

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        if not origins:
            raise ValueError("Configure at least one exact UI origin")
        for origin in origins:
            value = urlsplit(origin)
            if (
                value.scheme not in {"http", "https"}
                or not value.hostname
                or value.username is not None
                or value.password is not None
                or value.path
                or value.query
                or value.fragment
                or "*" in origin
                or (
                    value.scheme == "http"
                    and value.hostname not in {"127.0.0.1", "localhost", "::1"}
                )
            ):
                raise ValueError("Use exact HTTPS origins or HTTP loopback origins")
        return origins

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            # Validate without retaining a printable DSN in the settings model.
            try:
                dsn = PostgresDsn(value.get_secret_value())
                if dsn.scheme not in {"postgres", "postgresql"}:
                    raise ValueError
            except ValueError:
                raise ValueError("Use a valid postgres:// or postgresql:// URL") from None
        return value
