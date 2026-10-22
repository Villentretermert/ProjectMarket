"""Registry lifecycle, cross-tenant isolation and concurrent exchange on PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from marketob_api.bot_identity import authenticate_bot, require_bot_channel
from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.errors import ApiError
from marketob_api.identity import digest

from tests.test_identity import PASSWORD, business, channel, client, register
from tests.test_identity import settings as settings

pytestmark = pytest.mark.integration


def create_bot(http: TestClient, name: str = "Catalog") -> dict[str, Any]:
    response = http.post("/v1/bots", json={"name": name})
    assert response.status_code == 201
    return dict(response.json())


def exchange(http: TestClient, token: str) -> dict[str, Any]:
    response = http.post(
        "/v1/bot-registrations/exchange", json={}, headers={"Authorization": "Bearer " + token}
    )
    assert response.status_code == 201
    return dict(response.json())


def auth(key: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + key}


def test_self_service_lifecycle_stores_only_hashes(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    with client(settings) as owner, client(settings) as bot:
        register(owner, "alice")
        assert owner.post("/v1/bots", json={"name": "Shop"}).status_code == 403
        business(owner)
        registration = create_bot(owner)
        bot_id = registration["bot"]["bot_id"]
        assert registration["bot"]["state"] == "pending"
        assert owner.get("/v1/bots/" + bot_id).json()["last_seen"] is None
        token = registration["registration_credential"]
        key = exchange(bot, token)
        assert key["bot_id"] == bot_id
        assert (
            bot.post("/v1/bot-registrations/exchange", json={}, headers=auth(token)).status_code
            == 401
        )
        response = bot.get("/v1/bot/identity", headers=auth(key["api_key"]))
        assert response.status_code == 200 and response.json()["bot_id"] == bot_id
        assert response.headers["cache-control"] == "no-store"
        assert owner.get("/v1/bots/" + bot_id).json()["last_seen"] is not None
        inventory = owner.get("/v1/bots/" + bot_id + "/keys")
        assert inventory.json()["items"] == [key["key"]]
        assert key["api_key"] not in inventory.text + response.text + caplog.text
        assert token not in inventory.text + response.text + caplog.text
        assert (
            bot.post(
                "/v1/bots", json={"name": "Escalate"}, headers=auth(key["api_key"])
            ).status_code
            == 401
        )
    with Database(settings).transaction() as connection:
        row = connection.execute("SELECT * FROM bot_keys").fetchone()
        assert row and row["token_hash"] == digest(key["api_key"])
        assert key["api_key"] not in str(row)
        assert connection.execute("SELECT * FROM bot_registrations").fetchone() is None


def test_foreign_bots_channels_and_key_rotation(settings: Settings) -> None:
    with client(settings) as alice, client(settings) as bob, client(settings) as bot:
        register(alice, "alice")
        register(bob, "bob")
        org_a = business(alice)
        org_b = business(bob)
        a = create_bot(alice)
        b = create_bot(bob)
        aid, bid = a["bot"]["bot_id"], b["bot"]["bot_id"]
        key_a = exchange(bot, a["registration_credential"])
        key_b = exchange(bot, b["registration_credential"])
        assert alice.get("/v1/bots").json()["items"][0]["bot_id"] == aid
        assert alice.get("/v1/bots/" + bid).status_code == 404
        assert (
            alice.post("/v1/bots/" + bid + "/keys", json={"scopes": ["messages:write"]}).status_code
            == 404
        )
        assert alice.delete(f"/v1/bots/{aid}/keys/" + key_b["key"]["key_id"]).status_code == 404
        for extra in ({"org_id": org_b}, {"owner_user_id": "bob"}, {"state": "active"}):
            assert alice.post("/v1/bots", json={"name": "Forged", **extra}).status_code == 422
        own = channel(settings, org_a)
        foreign = channel(settings, org_b)
        with Database(settings).transaction() as connection:
            connection.execute(
                "UPDATE channel_access SET bot_id=%s WHERE channel_id=%s", (aid, own)
            )
            connection.execute(
                "UPDATE channel_access SET bot_id=%s WHERE channel_id=%s", (bid, foreign)
            )
            request = Request(
                {
                    "type": "http",
                    "headers": [(b"authorization", ("Bearer " + key_a["api_key"]).encode())],
                }
            )
            identity = authenticate_bot(connection, request, "messages:write")
            require_bot_channel(connection, identity, own)
            with pytest.raises(ApiError) as error:
                require_bot_channel(connection, identity, foreign)
            assert error.value.status == 404
        for invalid in (
            {"scopes": ["admin"]},
            {"scopes": ["events:read", "events:read"]},
            {"scopes": ["events:read"], "replaces_key_id": None},
        ):
            assert alice.post(f"/v1/bots/{aid}/keys", json=invalid).status_code == 422
        rotated = alice.post(
            f"/v1/bots/{aid}/keys",
            json={"scopes": ["events:read"], "replaces_key_id": key_a["key"]["key_id"]},
        )
        assert rotated.status_code == 201
        assert bot.get("/v1/bot/identity", headers=auth(key_a["api_key"])).status_code == 401
        new_key = rotated.json()["api_key"]
        assert bot.get("/v1/bot/identity", headers=auth(new_key)).status_code == 200
        with Database(settings).transaction() as connection:
            request = Request(
                {"type": "http", "headers": [(b"authorization", ("Bearer " + new_key).encode())]}
            )
            with pytest.raises(ApiError) as error:
                authenticate_bot(connection, request, "messages:write")
            assert error.value.status == 403
        assert (
            alice.delete(f"/v1/bots/{aid}/keys/" + rotated.json()["key"]["key_id"]).status_code
            == 204
        )
        assert bot.get("/v1/bot/identity", headers=auth(new_key)).status_code == 401


def test_bootstrap_expiry_renewal_and_credential_types(settings: Settings) -> None:
    with client(settings) as owner, client(settings) as bot:
        register(owner, "alice")
        business(owner)
        first = create_bot(owner)
        bot_id = first["bot"]["bot_id"]
        original = first["registration_credential"]
        with Database(settings).transaction() as connection:
            connection.execute("UPDATE bot_registrations SET expires_at=now()-interval '1 second'")
        assert (
            bot.post("/v1/bot-registrations/exchange", json={}, headers=auth(original)).status_code
            == 401
        )
        renewed = owner.post(f"/v1/bots/{bot_id}/registration", json={}).json()[
            "registration_credential"
        ]
        assert bot.get("/v1/bot/identity", headers=auth(renewed)).status_code == 401
        key = exchange(bot, renewed)["api_key"]
        assert (
            bot.post("/v1/bot-registrations/exchange", json={}, headers=auth(key)).status_code
            == 401
        )
        owner.post(f"/v1/bots/{bot_id}/registration", json={})
        assert bot.get("/v1/bot/identity", headers=auth(key)).status_code == 200
        with Database(settings).transaction() as connection:
            connection.execute("UPDATE bot_keys SET expires_at=now()-interval '1 second'")
        assert bot.get("/v1/bot/identity", headers=auth(key)).status_code == 401
        assert bot.get("/v1/bot/identity", headers=auth("mb_" + "x" * 43)).status_code == 401


def test_exchange_is_single_use_under_concurrency(settings: Settings) -> None:
    with client(settings) as owner:
        register(owner, "alice")
        business(owner)
        token = create_bot(owner)["registration_credential"]

    def perform(_: int) -> int:
        with client(settings) as bot:
            return bot.post(
                "/v1/bot-registrations/exchange", json={}, headers=auth(token)
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(perform, range(2))) == [201, 401]
    with Database(settings).transaction() as connection:
        assert connection.execute("SELECT count(*) AS count FROM bot_keys").fetchone() == {
            "count": 1
        }


def test_revoke_bot_and_account_disable_channels_and_keys(settings: Settings) -> None:
    with client(settings) as owner, client(settings) as bot:
        register(owner, "alice")
        org_id = business(owner)
        registration = create_bot(owner)
        bot_id = registration["bot"]["bot_id"]
        key = exchange(bot, registration["registration_credential"])["api_key"]
        source = channel(settings, org_id, "public")
        with Database(settings).transaction() as connection:
            connection.execute(
                "UPDATE channel_access SET bot_id=%s WHERE channel_id=%s", (bot_id, source)
            )
        assert owner.delete("/v1/bots/" + bot_id).status_code == 204
        assert owner.delete("/v1/bots/" + bot_id).status_code == 204
        assert bot.get("/v1/bot/identity", headers=auth(key)).status_code == 401
        assert owner.post(f"/v1/bots/{bot_id}/registration", json={}).status_code == 409
        with Database(settings).transaction() as connection:
            row = connection.execute(
                "SELECT * FROM channel_access WHERE channel_id=%s", (source,)
            ).fetchone()
            assert row and row["deleted_at"] is not None and not row["published"]
            assert connection.execute(
                "SELECT count(*) AS count FROM change_outbox WHERE channel_id=%s", (source,)
            ).fetchone() == {"count": 1}
        another = create_bot(owner)
        active = exchange(bot, another["registration_credential"])["api_key"]
        assert (
            owner.request("DELETE", "/v1/account", json={"password": PASSWORD}).status_code == 204
        )
        assert bot.get("/v1/bot/identity", headers=auth(active)).status_code == 401


def test_metadata_scans_and_quotas_survive_new_instance(settings: Settings) -> None:
    settings = settings.model_copy(update={"bot_read_rate_limit": 2})
    with client(settings) as owner, client(settings) as bot:
        register(owner, "alice")
        business(owner)
        first = create_bot(owner)
        second = create_bot(owner)
        page = owner.get("/v1/bots?limit=1").json()
        assert page["items"] == [first["bot"]]
        assert owner.get("/v1/bots", params={"cursor": page["next_cursor"]}).json()["items"] == [
            second["bot"]
        ]
        assert owner.get("/v1/bots?cursor=forged").status_code == 400
        key = exchange(bot, first["registration_credential"])["api_key"]
        assert bot.get("/v1/bot/identity", headers=auth(key)).status_code == 200
        assert bot.get("/v1/bot/identity", headers=auth(key)).status_code == 200
    with client(settings) as restarted:
        response = restarted.get("/v1/bot/identity", headers=auth(key))
        assert response.status_code == 429 and int(response.headers["retry-after"]) >= 1
