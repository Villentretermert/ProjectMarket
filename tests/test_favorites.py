"""Favorites across sessions, stale ordering, revisions and revoked/deleted sources."""

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from marketob_api.config import Settings
from marketob_api.database import Database

from tests.test_channels import edit, path, publish, validate
from tests.test_identity import PASSWORD, client, register
from tests.test_identity import settings as settings
from tests.test_ingestion import draft, message
from tests.test_ingestion import gateway as gateway

pytestmark = pytest.mark.integration


def test_bounded_collection_remains_readable_and_removable_at_limit(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source)
    user_id = owner.get("/v1/auth/session").json()["user"]["user_id"]
    org_id = owner.get("/v1/account/business-profile").json()["org_id"]
    with Database(settings).transaction() as connection:
        connection.execute(
            "INSERT INTO channel_access(channel_id,org_id,visibility) "
            "SELECT 'capacity_'||n,%s,'selected' FROM generate_series(1,100) n",
            (org_id,),
        )
        connection.execute(
            "INSERT INTO favorites(user_id,channel_id,position) "
            "SELECT %s,'capacity_'||n,n FROM generate_series(1,100) n",
            (user_id,),
        )
    url = "/v1/favorites/" + source["channel_id"]
    assert owner.put(url, json={}).json()["code"] == "favorites_limit"
    result = owner.get("/v1/favorites").json()
    validate("Favorites", result)
    assert len(result["items"]) == 100 and all(not r["available"] for r in result["items"])
    assert owner.delete("/v1/favorites/capacity_1").status_code == 204
    assert owner.put(url, json={}).status_code == 204


def ready(
    owner: TestClient, bot: TestClient, source: dict[str, Any], visibility: str = "public"
) -> None:
    assert (
        bot.post("/v1/bot/messages", json=message(source, mid=source["channel_id"])).status_code
        == 200
    )
    assert owner.put(path(source), json=edit(source, visibility=visibility)).status_code == 200
    publish(owner, source)


def test_favorites_sync_duplicate_order_conflict_and_independent_removal(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source)
    other = draft(owner, source["bot_id"], "other-source")
    ready(owner, bot, other)
    url = "/v1/favorites/" + source["channel_id"]
    with client(settings) as one, client(settings) as two, client(settings) as stranger:
        register(one, "reader")
        login = two.post("/v1/auth/login", json={"username": "reader", "password": PASSWORD})
        two.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        assert stranger.put(url, json={}).status_code == 401
        register(stranger, "stranger")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda c: c.put(url, json={}).status_code, (one, two)))
        assert results == [204, 204]
        saved = two.get("/v1/favorites").json()
        validate("Favorites", saved)
        assert saved["revision"] == 1 and len(saved["items"]) == 1
        assert stranger.get("/v1/favorites").json()["items"] == []
        assert one.put("/v1/favorites/" + other["channel_id"], json={}).status_code == 204
        ordered = {
            "expected_revision": 2,
            "channel_ids": [other["channel_id"], source["channel_id"]],
        }
        assert two.put("/v1/favorites/order", json=ordered).json() == {"revision": 3}
        assert one.put("/v1/favorites/order", json=ordered).status_code == 409
        assert [r["channel_id"] for r in one.get("/v1/favorites").json()["items"]] == ordered[
            "channel_ids"
        ]
        assert (
            two.put(
                "/v1/favorites/order", json={"expected_revision": 3, "channel_ids": []}
            ).status_code
            == 409
        )
        assert one.delete(url).status_code == 204
        assert one.delete(url).status_code == 204
        assert two.get("/v1/favorites").json()["revision"] == 4
        assert one.get("/v1/channels/" + source["slug"]).status_code == 200


def test_seen_marks_observed_revisions_without_consuming_newer_data(
    gateway: tuple[TestClient, TestClient, dict[str, Any]],
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source)
    url = "/v1/favorites/" + source["channel_id"]
    assert owner.put(url, json={}).status_code == 204
    assert owner.get("/v1/favorites").json()["items"][0]["unread"]
    observed = {"data_revision": 1, "template_version": 2}
    assert bot.post("/v1/bot/messages", json=message(source, 2, "new_data")).status_code == 200
    assert owner.put(url + "/seen", json=observed).status_code == 204
    assert owner.get("/v1/favorites").json()["items"][0]["unread"]
    assert owner.put(url + "/seen", json={**observed, "data_revision": 2}).status_code == 204
    assert owner.put(url + "/seen", json=observed).status_code == 204
    assert not owner.get("/v1/favorites").json()["items"][0]["unread"]
    assert owner.put(url + "/seen", json={**observed, "data_revision": 999}).status_code == 409
    current = owner.get(path(source)).json()
    assert owner.put(path(source), json=edit(current, visibility="public")).status_code == 200
    publish(owner, source, 3)
    assert owner.get("/v1/favorites").json()["items"][0]["unread"]


def test_favorite_revocation_and_deletion_return_reference_only(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source, "selected")
    url = "/v1/favorites/" + source["channel_id"]
    with client(settings) as reader:
        user = register(reader, "reader")
        assert reader.put(url, json={}).status_code == 404
        grant = path(source, "/grants/" + user)
        assert owner.put(grant, json={}).status_code == 204
        assert reader.put(url, json={}).status_code == 204
        assert reader.get("/v1/favorites").json()["items"][0]["title"] == source["title"]
        assert owner.delete(grant).status_code == 204
        assert reader.get("/v1/favorites").json()["items"] == [
            {"channel_id": source["channel_id"], "available": False}
        ]
        assert (
            reader.put(url + "/seen", json={"data_revision": 1, "template_version": 2}).status_code
            == 404
        )
        assert owner.put(grant, json={}).status_code == 204
        assert reader.get("/v1/favorites").json()["items"][0]["available"]
        assert owner.delete(path(source)).status_code == 204
        assert reader.get("/v1/favorites").json()["items"] == [
            {"channel_id": source["channel_id"], "available": False}
        ]
        assert reader.delete(url).status_code == 204


def test_favorites_reject_payload_injection_and_duplicate_order(
    gateway: tuple[TestClient, TestClient, dict[str, Any]],
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source)
    url = "/v1/favorites/" + source["channel_id"]
    assert owner.put(url, json={"user_id": "other"}).status_code == 422
    assert owner.put(url, json={}).status_code == 204
    assert (
        owner.put(
            "/v1/favorites/order",
            json={"expected_revision": 1, "channel_ids": [source["channel_id"]] * 2},
        ).status_code
        == 422
    )
    assert (
        owner.put(url + "/seen", json={"data_revision": -1, "template_version": 2}).status_code
        == 422
    )
