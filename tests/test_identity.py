"""Real PostgreSQL identity and access tests in a fresh schema per scenario."""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from marketob_api.access import require_owner, require_read
from marketob_api.app import create_app
from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.errors import ApiError
from marketob_api.identity import COOKIE, digest
from marketob_api.migrate import migrate
from psycopg import sql
from pydantic import SecretStr

pytestmark = pytest.mark.integration
ORIGIN = "http://127.0.0.1:8000"
PASSWORD = "synthetic-password-for-tests"


@pytest.fixture
def settings() -> Iterator[Settings]:
    configured_url = os.environ.get("MARKETOB_TEST_DATABASE_URL")
    if not configured_url:
        pytest.skip("A dedicated PostgreSQL test database is required")
    url = SecretStr(configured_url)
    del configured_url
    schema = "test_" + uuid4().hex
    with psycopg.connect(url.get_secret_value(), autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    value = Settings(
        _env_file=None,
        database_url=url,
        database_schema=schema,
        allowed_origins=[ORIGIN, "http://127.0.0.1:8100", "https://marketob.example"],
        auth_rate_limit=100,
    )
    try:
        migrate(Database(value))
        yield value
    finally:
        # Only the random schema created by this test is removed, never a database.
        assert schema.startswith("test_") and len(schema) == 37
        with psycopg.connect(url.get_secret_value(), autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings), base_url=ORIGIN, headers={"Origin": ORIGIN})


def register(http: TestClient, username: str) -> str:
    response = http.post(
        "/v1/auth/register",
        json={"username": username, "password": PASSWORD, "display_name": username.title()},
    )
    assert response.status_code == 201, response.text
    http.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return str(response.json()["user"]["user_id"])


def business(http: TestClient) -> str:
    response = http.put("/v1/account/business-profile", json={"name": "Test shop"})
    assert response.status_code == 200, response.text
    return str(response.json()["org_id"])


def channel(settings: Settings, org_id: str, visibility: str = "selected") -> str:
    channel_id = "ch_" + uuid4().hex
    with Database(settings).transaction() as connection:
        connection.execute(
            "INSERT INTO channel_access(channel_id,org_id,visibility,published) "
            "VALUES (%s,%s,%s,true)",
            (channel_id, org_id, visibility),
        )
    return channel_id


def test_migrations_repeat_and_reject_mutated_history(settings: Settings) -> None:
    database = Database(settings)
    assert migrate(database) == []
    with database.transaction() as connection:
        connection.execute("UPDATE schema_migrations SET checksum='changed'")
    with pytest.raises(RuntimeError, match="Applied migration changed"):
        migrate(database)


def test_password_and_cookie_are_not_stored_raw(settings: Settings) -> None:
    with client(settings) as http:
        user_id = register(http, "alice")
        token = http.cookies[COOKIE]
        response = http.get("/v1/auth/session")
        assert response.status_code == 200
        assert token not in response.text and PASSWORD not in response.text
        expires = datetime.fromisoformat(response.json()["expires_at"])
        assert expires.utcoffset() == datetime.now(UTC).utcoffset()
        assert 23 * 3600 < (expires - datetime.now(UTC)).total_seconds() <= 24 * 3600
    with Database(settings).transaction() as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE user_id=%s", (user_id,)
        ).fetchone()
        assert row and row["password_hash"].startswith("$argon2id$")
        assert PASSWORD not in row["password_hash"]
        session = connection.execute("SELECT token_hash FROM sessions").fetchone()
        assert session and session["token_hash"] == digest(token)


def test_wrong_password_and_nonexistent_user_share_safe_error(settings: Settings) -> None:
    with client(settings) as http:
        register(http, "alice")
        responses = [
            http.post("/v1/auth/login", json={"username": name, "password": "invalid-password"})
            for name in ("alice", "nobody")
        ]
    assert all(response.status_code == 401 for response in responses)
    for response in responses:
        assert response.json()["code"] == "invalid_credentials"
        assert response.json()["message"] == "Username or password is incorrect."
        assert "invalid-password" not in response.text


def test_forged_expired_wrong_client_and_logout(settings: Settings) -> None:
    with client(settings) as http:
        register(http, "alice")
        token = http.cookies[COOKIE]
        http.cookies.clear()
        http.cookies.set(COOKIE, "ms_" + "x" * 43, domain="127.0.0.1", path="/")
        assert http.get("/v1/auth/session").status_code == 401
        http.cookies.clear()
        http.cookies.set(COOKIE, token, domain="127.0.0.1", path="/")
        assert (
            http.get("/v1/auth/session", headers={"Origin": "http://127.0.0.1:8100"}).status_code
            == 401
        )
        with Database(settings).transaction() as connection:
            connection.execute("UPDATE sessions SET expires_at=now()-interval '1 second'")
        assert http.get("/v1/auth/session").status_code == 401
        response = http.post("/v1/auth/login", json={"username": "alice", "password": PASSWORD})
        assert response.status_code == 200
        http.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        current_token = http.cookies[COOKIE]
        response = http.delete("/v1/auth/session")
        assert response.status_code == 204 and "Max-Age=0" in response.headers["set-cookie"]
        http.cookies.clear()
        http.cookies.set(COOKIE, current_token, domain="127.0.0.1", path="/")
        assert http.get("/v1/auth/session").status_code == 401


def test_origin_csrf_and_cookie_flags(settings: Settings) -> None:
    with client(settings) as http:
        response = http.post(
            "/v1/auth/register",
            headers={"Origin": "https://evil.example"},
            json={
                "username": "alice",
                "password": PASSWORD,
                "display_name": "Alice",
            },
        )
        assert response.status_code == 403
        response = http.post(
            "/v1/auth/register",
            json={
                "username": "alice",
                "password": PASSWORD,
                "display_name": "Alice",
            },
        )
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/" in cookie
        assert "Secure" not in cookie
        assert http.put("/v1/account/business-profile", json={"name": "Shop"}).status_code == 403
        http.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        business(http)
    with TestClient(create_app(settings), base_url="https://marketob.example") as secure:
        response = secure.post(
            "/v1/auth/login",
            headers={"Origin": "https://marketob.example"},
            json={
                "username": "alice",
                "password": PASSWORD,
            },
        )
        assert response.status_code == 200
        assert "Secure" in response.headers["set-cookie"]


def test_rate_limit_counts_failed_auth_and_survives_new_app(settings: Settings) -> None:
    settings = settings.model_copy(update={"auth_rate_limit": 2})
    with client(settings) as http:
        for _ in range(2):
            assert (
                http.post(
                    "/v1/auth/login", json={"username": "nobody", "password": PASSWORD}
                ).status_code
                == 401
            )
    with client(settings) as http:
        response = http.post("/v1/auth/login", json={"username": "nobody", "password": PASSWORD})
        assert response.status_code == 429
        assert 1 <= int(response.headers["retry-after"]) <= 60


def test_role_and_user_injection_are_rejected(settings: Settings) -> None:
    with client(settings) as http:
        response = http.post(
            "/v1/auth/register",
            json={
                "username": "alice",
                "password": PASSWORD,
                "display_name": "Alice",
                "role": "admin",
            },
        )
        assert response.status_code == 422 and PASSWORD not in response.text
        register(http, "alice")
        for extra in ({"role": "owner"}, {"user_id": "someone"}, {"org_id": "foreign"}):
            assert (
                http.put("/v1/account/business-profile", json={"name": "Shop", **extra}).status_code
                == 422
            )


def test_owner_reader_and_anonymous_access_are_distinct(settings: Settings) -> None:
    database = Database(settings)
    with client(settings) as alice, client(settings) as bob, client(settings) as carol:
        owner = register(alice, "alice")
        reader = register(bob, "bob")
        stranger = register(carol, "carol")
        org = business(alice)
        private = channel(settings, org)
        public = channel(settings, org, "public")
        endpoint = f"/v1/owner/channels/{private}/grants/{reader}"
        assert bob.put(endpoint, json={}).status_code == 403
        business(bob)
        assert bob.put(endpoint, json={}).status_code == 404
        assert alice.put(endpoint, json={}).status_code == 204
        lookup = alice.get("/v1/users/by-username/bob")
        assert lookup.status_code == 200 and lookup.json()["user_id"] == reader
        assert set(lookup.json()) == {"user_id", "username", "display_name"}
        assert carol.get("/v1/users/by-username/bob").status_code == 403
        with database.transaction() as connection:
            require_owner(connection, private, owner)
            require_read(connection, private, reader)
            require_read(connection, public, None)
            for user in (stranger, None):
                with pytest.raises(ApiError) as error:
                    require_read(connection, private, user)
                assert error.value.status == 404
        assert alice.delete(endpoint).status_code == 204
        with database.transaction() as connection:
            with pytest.raises(ApiError, match="source_unavailable"):
                require_read(connection, private, reader)
            assert connection.execute(
                "SELECT 1 FROM change_outbox WHERE kind='access.revoked'"
            ).fetchone()
        assert alice.delete(endpoint).status_code == 204


def test_grant_cursor_is_signed_and_bound_to_session(settings: Settings) -> None:
    with client(settings) as alice, client(settings) as bob, client(settings) as carol:
        register(alice, "alice")
        bob_id = register(bob, "bob")
        carol_id = register(carol, "carol")
        source = channel(settings, business(alice))
        endpoint = f"/v1/owner/channels/{source}/grants"
        for user_id in (bob_id, carol_id):
            assert alice.put(endpoint + "/" + user_id, json={}).status_code == 204
        first = alice.get(endpoint, params={"limit": 1}).json()
        cursor = first["next_cursor"]
        assert cursor and len(first["items"]) == 1
        second = alice.get(endpoint, params={"limit": 1, "cursor": cursor})
        assert second.status_code == 200 and second.json()["next_cursor"] is None
        assert second.json()["items"] != first["items"]
        assert alice.get(endpoint, params={"cursor": "x" + cursor[1:]}).status_code == 400
        login = alice.post("/v1/auth/login", json={"username": "alice", "password": PASSWORD})
        assert login.status_code == 200
        assert alice.get(endpoint, params={"cursor": cursor}).status_code == 400


def test_deactivation_revokes_all_sessions_and_owned_sources(settings: Settings) -> None:
    with client(settings) as alice, client(settings) as other:
        user_id = register(alice, "alice")
        source = channel(settings, business(alice), "public")
        assert (
            other.post(
                "/v1/auth/login", json={"username": "alice", "password": PASSWORD}
            ).status_code
            == 200
        )
        response = alice.request("DELETE", "/v1/account", json={"password": PASSWORD})
        assert response.status_code == 204
        assert other.get("/v1/auth/session").status_code == 401
        assert (
            other.post(
                "/v1/auth/login", json={"username": "alice", "password": PASSWORD}
            ).status_code
            == 401
        )
        with Database(settings).transaction() as connection:
            with pytest.raises(ApiError):
                require_read(connection, source, None)
            row = connection.execute("SELECT * FROM users WHERE user_id=%s", (user_id,)).fetchone()
            assert row and row["password_hash"] is None and row["display_name"] == "Deleted user"
