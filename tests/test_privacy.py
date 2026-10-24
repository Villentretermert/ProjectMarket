"""Privacy cleanup must preserve other users' delivery and unresolved bot requests."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.maintenance import prune_private_metadata, prune_updates

from tests.test_actions import event_path, queue
from tests.test_actions import shop as shop
from tests.test_channels import path
from tests.test_favorites import ready
from tests.test_identity import PASSWORD, client, register
from tests.test_identity import settings as settings
from tests.test_ingestion import draft, message
from tests.test_ingestion import gateway as gateway
from tests.test_updates import poll

pytestmark = pytest.mark.integration


def choose(http: TestClient, channel_id: str) -> None:
    assert (
        http.put(
            "/v1/preferences/" + channel_id,
            json={"channel_id": channel_id, "events": ["news.published"]},
        ).status_code
        == 200
    )


def test_deleted_user_preferences_and_hints_removed_without_losing_request(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, bot, customer, source, user_id = shop
    request = queue(customer, source)
    acknowledged = queue(customer, source, "already-acknowledged")
    event = next(
        item
        for item in bot.get("/v1/bot/events").json()["items"]
        if item["action_request_id"] == acknowledged["action_request_id"]
    )
    assert bot.post(event_path(event, "ack"), json={}).status_code == 200
    choose(customer, source["channel_id"])
    choose(owner, source["channel_id"])
    assert customer.request("DELETE", "/v1/account", json={"password": PASSWORD}).status_code == 204
    database = Database(settings)
    result = prune_private_metadata(database)
    assert result["privacy_preferences"] == 1 and result["privacy_updates"] >= 1
    with database.transaction() as connection:
        assert not connection.execute(
            "SELECT 1 FROM event_preferences WHERE user_id=%s", (user_id,)
        ).fetchone()
        assert not connection.execute(
            "SELECT 1 FROM change_outbox WHERE user_id=%s", (user_id,)
        ).fetchone()
        assert connection.execute("SELECT count(*) n FROM event_preferences").fetchone() == {"n": 1}
        row = connection.execute(
            "SELECT state FROM action_requests WHERE action_request_id=%s",
            (request["action_request_id"],),
        ).fetchone()
        # Unacknowledged requests retain the established cancellation/reconciliation policy.
        assert row and row["state"] == "cancelled"
        pending = connection.execute(
            "SELECT state FROM action_requests WHERE action_request_id=%s",
            (acknowledged["action_request_id"],),
        ).fetchone()
        assert pending and pending["state"] == "unknown"
    assert prune_private_metadata(database) == {"privacy_preferences": 0, "privacy_updates": 0}


def test_deleted_source_cleanup_preserves_revocation_and_other_delivery_ids(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source)
    other = draft(owner, source["bot_id"], "unaffected-source")
    ready(owner, bot, other)
    database = Database(settings)
    with client(settings) as reader:
        register(reader, "privacy_reader")
        for item in (source, other):
            choose(reader, item["channel_id"])
            assert reader.put("/v1/favorites/" + item["channel_id"], json={}).status_code == 204
        cursor = poll(reader)["next_cursor"]
        assert (
            bot.post("/v1/bot/messages", json=message(source, 2, "private-old")).status_code == 200
        )
        assert bot.post("/v1/bot/messages", json=message(other, 2, "keep-me")).status_code == 200
        delivered = poll(reader, cursor)
        preserved = next(i for i in delivered["items"] if i["channel_id"] == other["channel_id"])
        assert owner.delete(path(source)).status_code == 204
        # Existing deployments may still contain legacy revocation hints during an upgrade.
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO change_outbox(channel_id,kind) VALUES (%s,'access.revoked')",
                (source["channel_id"],),
            )
        result = prune_private_metadata(database)
        assert result["privacy_preferences"] == 1 and result["privacy_updates"] > 0
        assert reader.get("/v1/updates", params={"cursor": cursor}).status_code == 410
        recovered = poll(reader, watch=source["channel_id"])
        assert any(i["kind"] == "access.revoked" for i in recovered["items"])
        with database.transaction() as connection:
            assert connection.execute(
                "SELECT 1 FROM change_outbox WHERE channel_id=%s AND delivery_sequence=%s",
                (other["channel_id"], int(preserved["update_id"].split("_")[1])),
            ).fetchone()
            remaining = connection.execute(
                "SELECT * FROM change_outbox WHERE channel_id=%s", (source["channel_id"],)
            ).fetchall()
            assert remaining and all(r["kind"] == "access.revoked" for r in remaining)
            assert all(r["user_id"] is None and r["resource_id"] is None for r in remaining)
            before = connection.execute("SELECT * FROM delivery_state").fetchone()
            assert before
            connection.execute("UPDATE change_outbox SET delivered_at=now()-interval '2 hours'")
        assert prune_updates(database) > 0
        assert reader.get("/v1/updates", params={"cursor": cursor}).status_code == 410
        fresh = poll(reader)["next_cursor"]
        assert (
            bot.post("/v1/bot/messages", json=message(other, 3, "after-cleanup")).status_code == 200
        )
        new = poll(reader, fresh)["items"][0]
        assert int(new["update_id"].split("_")[1]) > before["watermark"]


def test_cleanup_is_bounded_and_covers_owner_deactivation(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source)
    with client(settings) as reader:
        register(reader, "remaining_reader")
        choose(owner, source["channel_id"])
        choose(reader, source["channel_id"])
        assert (
            owner.request("DELETE", "/v1/account", json={"password": PASSWORD}).status_code == 204
        )
        database = Database(settings)
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO change_outbox(channel_id,kind) VALUES (%s,'source.deleted')",
                (source["channel_id"],),
            )
        first = prune_private_metadata(database, batch=1)
        assert first["privacy_preferences"] == 1 and first["privacy_updates"] <= 1
        second = prune_private_metadata(database)
        assert second["privacy_preferences"] == 1
        with database.transaction() as connection:
            assert not connection.execute("SELECT 1 FROM event_preferences").fetchone()
            assert connection.execute(
                "SELECT 1 FROM change_outbox WHERE kind='source.deleted' AND user_id IS NULL"
            ).fetchone()
