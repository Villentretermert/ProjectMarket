"""Environment configuration with optional storage for foundation smoke tests."""

from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
    database_url: SecretStr | None = None
    database_timeout_seconds: int = Field(default=3, ge=2, le=30)

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
