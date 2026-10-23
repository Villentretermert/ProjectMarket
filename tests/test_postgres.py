"""Real PostgreSQL check; ordinary unit runs need no environment secrets."""

import pytest
from fastapi.testclient import TestClient
from marketob_api.app import create_app
from marketob_api.config import Settings

from tests.test_identity import settings as settings


@pytest.mark.integration
def test_real_postgres_readiness(settings: Settings) -> None:
    with TestClient(create_app(settings)) as http:
        response = http.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}
