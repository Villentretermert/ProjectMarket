"""Hostile protocol input is rejected before storage or password processing."""

import pytest
from fastapi.testclient import TestClient
from marketob_api.app import create_app
from marketob_api.config import Settings


@pytest.mark.parametrize(
    "body,content_type,status",
    [
        (b'{"username":"alice","username":"bob"}', "application/json", 400),
        (b'{"value":NaN}', "application/json", 400),
        (b'{"value":1e9999}', "application/json", 400),
        (b'"\xff"', "application/json", 400),
        (b"x" * 262145, "application/json", 413),
        (b"{}", "text/plain", 415),
        (b'{"role":"admin"}', "application/json", 422),
    ],
    ids=[
        "duplicate-key",
        "nan",
        "infinity",
        "non-utf8",
        "oversized",
        "media-type",
        "unknown-field",
    ],
)
def test_invalid_wire_input(body: bytes, content_type: str, status: int) -> None:
    with TestClient(create_app(Settings(_env_file=None))) as http:
        response = http.post(
            "/v1/auth/register", content=body, headers={"Content-Type": content_type}
        )
    assert response.status_code == status
    assert set(response.json()) == {"code", "message", "request_id", "retryable"}
    assert response.headers["cache-control"] == "no-store"


def test_compression_and_untrusted_preflight_rejected() -> None:
    with TestClient(create_app(Settings(_env_file=None))) as http:
        compressed = http.post(
            "/v1/auth/register", content=b"abc", headers={"Content-Encoding": "gzip"}
        )
        preflight = http.options(
            "/v1/auth/register",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert compressed.status_code == 415
    assert "access-control-allow-origin" not in preflight.headers
