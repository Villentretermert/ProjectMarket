"""Real PostgreSQL check; ordinary unit runs need no environment secrets."""

import os

import pytest
from fastapi.testclient import TestClient
from marketob_api.app import create_app
from marketob_api.config import Settings
from pydantic import SecretStr


@pytest.mark.integration
def test_real_postgres_readiness() -> None:
    url = os.environ.get("MARKETOB_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set MARKETOB_TEST_DATABASE_URL to a disposable PostgreSQL database")
    settings = Settings(_env_file=None, database_url=SecretStr(url))
    with TestClient(create_app(settings)) as http:
        response = http.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}
