"""Commit ordering, resumable delivery and current authorization on real PostgreSQL."""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from marketob_api.config import Settings
from marketob_api.cursors import Scan, encode_scan, session_binding
from marketob_api.database import Database
from marketob_api.identity import COOKIE

from tests.test_actions import queue
from tests.test_actions import shop as shop
from tests.test_channels import path, validate
from tests.test_favorites import ready
from tests.test_identity import PASSWORD, client, register
from tests.test_identity import settings as settings
from tests.test_ingestion import draft, message
from tests.test_ingestion import gateway as gateway
from tests.test_personal_pages import body, create

pytestmark = pytest.mark.integration


def poll(http: TestClient, cursor: str | None = None, watch: str | None = None) -> dict[str, Any]:
    params = {k: v for k, v in {"cursor": cursor, "watch": watch}.items() if v}
    response = http.get("/v1/updates", params=params)
    assert response.status_code == 200, response.text
    value = response.json()
    validate("UpdatePage", value)
    return dict(value)


def test_interest_preferences_privacy_revocation_and_restoration(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source, "selected")
    cid = source["channel_id"]
    other = draft(owner, source["bot_id"], "other-public")
    ready(owner, bot, other)
    with client(settings) as reader, client(settings) as stranger:
        uid = register(reader, "reader")
        register(stranger, "stranger")
        assert owner.put(path(source, "/grants/" + uid), json={}).status_code == 204
        assert reader.put("/v1/favorites/" + cid, json={}).status_code == 204
        cursor = poll(reader)["next_cursor"]
        foreign = poll(stranger)["next_cursor"]
        assert bot.post("/v1/bot/messages", json=message(source, 2, "second")).status_code == 200
        updates = poll(reader, cursor)
        assert len(updates["items"]) == 1 and not updates["items"][0]["notify"]
        assert "Synthetic news" not in str(updates) and "Local pilot" not in str(updates)
        assert poll(stranger, foreign)["items"] == []
        default = reader.get("/v1/preferences/" + cid).json()
        assert default["events"] == ["request.status"]
        chosen = {"channel_id": cid, "events": ["news.published"]}
        assert reader.put("/v1/preferences/" + cid, json=chosen).json() == chosen
        assert stranger.put("/v1/preferences/" + cid, json=chosen).status_code == 404
        assert reader.get("/v1/preferences").json()["items"] == [chosen]
        assert bot.post("/v1/bot/messages", json=message(source, 3, "third")).status_code == 200
        assert bot.post("/v1/bot/messages", json=message(other, 2, "unfollowed")).status_code == 200
        page = poll(reader, updates["next_cursor"])
        assert len(page["items"]) == 1 and page["items"][0]["notify"]
        assert owner.delete(path(source, "/grants/" + uid)).status_code == 204
        revoked = poll(reader, page["next_cursor"], cid)
        assert all(i["kind"] == "access.revoked" and not i["notify"] for i in revoked["items"])
        assert reader.get("/v1/preferences").json()["items"] == []
        assert owner.put(path(source, "/grants/" + uid), json={}).status_code == 204
        restored = poll(reader, revoked["next_cursor"], cid)
        assert restored["items"][0]["kind"] == "channel.changed"
        assert owner.delete(path(source, "/grants/" + uid)).status_code == 204
        assert poll(reader, restored["next_cursor"], cid)["items"][0]["kind"] == "access.revoked"
        # Rechecking a displayed ID never returns an unknown source's metadata.
        assert poll(stranger, watch="unknown")["items"][0]["target_id"] == "unknown"


def test_late_commit_gets_later_delivery_and_replay_is_stable(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source)
    cid = source["channel_id"]
    cursor = poll(owner)["next_cursor"]
    database = Database(settings)
    with database.transaction() as delayed:
        late = delayed.execute(
            "INSERT INTO change_outbox(channel_id,kind,data_revision) "
            "VALUES (%s,'channel.changed',10) RETURNING sequence",
            (cid,),
        ).fetchone()
        with database.transaction() as fast:
            early = fast.execute(
                "INSERT INTO change_outbox(channel_id,kind,data_revision) "
                "VALUES (%s,'channel.changed',11) RETURNING sequence",
                (cid,),
            ).fetchone()
        assert late and early and late["sequence"] < early["sequence"]
        first = poll(owner, cursor, cid)
        assert [i["revision"] for i in first["items"]] == [11]
        assert poll(owner, cursor, cid)["items"] == first["items"]
    second = poll(owner, first["next_cursor"], cid)
    assert [i["revision"] for i in second["items"]] == [10]
    assert int(second["items"][0]["update_id"].split("_")[1]) > int(
        first["items"][0]["update_id"].split("_")[1]
    )
    assert poll(owner, second["next_cursor"], cid)["items"] == []


def test_cursor_expiry_session_binding_bootstrap_and_bounded_scan(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source)
    cid = source["channel_id"]
    initial = poll(owner)
    assert initial["items"] == []
    token = initial["next_cursor"]
    assert owner.get("/v1/updates", params={"cursor": token[:-4] + "xxxx"}).status_code == 400
    with client(settings) as other:
        other.post("/v1/auth/login", json={"username": "alice", "password": PASSWORD})
        assert other.get("/v1/updates", params={"cursor": token}).status_code == 400
    with Database(settings).transaction() as db:
        expired = encode_scan(
            db, session_binding(owner.cookies[COOKIE], "updates"), Scan(0, 0, int(time.time()) - 1)
        )
        db.execute(
            "INSERT INTO change_outbox(channel_id,kind,data_revision) "
            "SELECT %s,'channel.changed',n FROM generate_series(1,130) n",
            (cid,),
        )
    assert owner.get("/v1/updates", params={"cursor": expired}).status_code == 410
    ids: list[str] = []
    while True:
        value = poll(owner, token, cid)
        ids.extend(i["update_id"] for i in value["items"])
        token = value["next_cursor"]
        if not value["has_more"]:
            break
    assert len(ids) == len(set(ids)) == 130
    assert poll(owner)["items"] == []
    assert owner.get("/v1/updates", params=[("watch", cid)] * 51).status_code == 422
    assert owner.get("/v1/updates", params={"watch": "bad/id"}).status_code == 422
    assert owner.delete("/v1/auth/session").status_code == 204
    assert owner.get("/v1/updates", params={"cursor": token}).status_code == 401


def test_only_actor_receives_request_notifications(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, _, customer, source, _ = shop
    cid = source["channel_id"]
    own_cursor, owner_cursor = poll(customer)["next_cursor"], poll(owner)["next_cursor"]
    request = queue(customer, source)
    value = poll(customer, own_cursor)
    assert len(value["items"]) == 1
    assert value["items"][0]["target_id"] == request["action_request_id"]
    assert value["items"][0]["notify"] and "summary" not in str(value)
    assert poll(owner, owner_cursor, cid)["items"] == []
    assert (
        customer.put("/v1/preferences/" + cid, json={"channel_id": cid, "events": []}).status_code
        == 200
    )
    queue(customer, source, "second_purchase")
    assert not poll(customer, value["next_cursor"])["items"][0]["notify"]
    assert (
        customer.put(
            "/v1/preferences/" + cid, json={"channel_id": "wrong", "events": []}
        ).status_code
        == 422
    )


def test_personal_references_and_restarted_apps_share_a_durable_cursor(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source)
    with client(settings) as reader:
        register(reader, "personal_reader")
        create(reader, body(owner.get(path(source)).json()))
        assert reader.get("/v1/favorites").json()["items"] == []
        cursor = poll(reader)["next_cursor"]
        assert (
            bot.post("/v1/bot/messages", json=message(source, 2, "after_restart")).status_code
            == 200
        )
        # Independent app factories use the persisted session/cursor key and one delivery order.
        with client(settings) as restarted, client(settings) as concurrent:
            for http in (restarted, concurrent):
                http.cookies.update(reader.cookies)
            with ThreadPoolExecutor(max_workers=2) as pool:
                one, two = list(pool.map(lambda http: poll(http, cursor), [restarted, concurrent]))
            assert one["items"] == two["items"]
            assert len(one["items"]) == 1 and one["items"][0]["channel_id"] == source["channel_id"]
            assert poll(restarted, one["next_cursor"])["items"] == []
