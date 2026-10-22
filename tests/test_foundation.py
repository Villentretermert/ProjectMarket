"""Operational behavior and configuration failures, without a live database."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg
import pytest
from fastapi.testclient import TestClient
from marketob_api.app import create_app
from marketob_api.config import Settings
from pydantic import SecretStr, ValidationError

from scripts.dev_env import create_env


@contextmanager
def client(settings: Settings | None = None) -> Generator[TestClient]:
    with TestClient(create_app(settings or Settings(_env_file=None))) as connection:
        yield connection


def test_liveness_requires_no_secrets_or_database() -> None:
    with client() as http:
        response = http.get("/health/live")
    assert response.status_code == 200
    assert response.json()["service"] == "marketob-api"
    assert response.headers["cache-control"] == "no-store"


def test_missing_database_is_not_ready_and_does_not_connect() -> None:
    with patch("marketob_api.health.psycopg.connect") as connect, client() as http:
        response = http.get("/health/ready")
    connect.assert_not_called()
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "not_configured"}


def configured() -> Settings:
    return Settings(
        _env_file=None,
        database_url=SecretStr("postgresql://test:synthetic-test-password@localhost/test"),
    )


def test_database_failure_is_sanitized_and_liveness_survives() -> None:
    error = psycopg.OperationalError("synthetic-test-password internal-host")
    with (
        patch("marketob_api.health.psycopg.connect", side_effect=error),
        client(configured()) as http,
    ):
        response = http.get("/health/ready")
        assert http.get("/health/live").status_code == 200
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
    assert "synthetic-test-password" not in response.text
    assert "internal-host" not in response.text


@pytest.mark.parametrize("row,code", [((1,), 200), (None, 503)])
def test_readiness_requires_successful_query(row: tuple[int] | None, code: int) -> None:
    connection = MagicMock()
    cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = row
    with (
        patch("marketob_api.health.psycopg.connect", return_value=connection),
        client(configured()) as http,
    ):
        response = http.get("/health/ready")
    cursor.execute.assert_called_once_with("SELECT 1")
    assert response.status_code == code
    connection.__exit__.assert_called_once()


def test_runtime_spec_does_not_claim_future_business_endpoints() -> None:
    with client() as http:
        spec = http.get("/openapi.json").json()
        assert http.get("/v1/bot/messages").status_code == 405
        assert http.get("/v1/bot/events").status_code == 404
        assert http.get("/docs").status_code == 404  # No external CDN for local docs.
    assert {"/health/live", "/health/ready", "/v1/auth/session"} <= set(spec["paths"])
    assert "post" in spec["paths"]["/v1/bot/messages"]
    assert "/v1/bot/events" not in spec["paths"]


def test_environment_overrides_file_without_disclosing_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / ".env"
    path.write_text("MARKETOB_PORT=8100\nPOSTGRES_PASSWORD=irrelevant\n", encoding="utf-8")
    monkeypatch.setenv("MARKETOB_PORT", "8200")
    settings = Settings(_env_file=path)
    assert settings.port == 8200
    assert settings.host == "127.0.0.1"
    assert "synthetic-test-password" not in repr(configured())


@pytest.mark.parametrize("value", ["0", "65536", "not-a-port"])
def test_invalid_port_rejected(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETOB_PORT", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "value", ["", "sqlite:///private", "postgresql+asyncpg://user:private@localhost/db"]
)
def test_invalid_database_url_fails_without_exposing_input(value: str) -> None:
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_url=SecretStr(value))
    assert "private" not in str(error.value)


def test_dev_env_never_overwrites_existing_configuration(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    create_env(path)
    original = path.read_bytes()
    assert b"POSTGRES_PASSWORD=" in original
    other = tmp_path / ".env.other"
    create_env(other)
    assert other.read_bytes() != original
    with pytest.raises(FileExistsError):
        create_env(path)
    assert path.read_bytes() == original
