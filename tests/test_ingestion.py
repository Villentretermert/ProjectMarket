"""Real database acceptance: retries, ordering, rollback, tenants and retention."""

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.maintenance import prune

from tests.test_bots import auth, create_bot, exchange
from tests.test_identity import business, client, register
from tests.test_identity import settings as settings

pytestmark = pytest.mark.integration


def draft(owner: TestClient, bot_id: str, slug: str = "test-catalog") -> dict[str, Any]:
    response = owner.post(
        "/v1/channels",
        json={"bot_id": bot_id, "slug": slug, "title": "Test catalog", "visibility": "selected"},
    )
    assert response.status_code == 201
    return dict(response.json())


@pytest.fixture
def gateway(settings: Settings) -> Iterator[tuple[TestClient, TestClient, dict[str, Any]]]:
    with client(settings) as owner, client(settings) as bot:
        register(owner, "alice")
        business(owner)
        registration = create_bot(owner)
        key = exchange(bot, registration["registration_credential"])
        bot.headers.update(auth(key["api_key"]))
        source = draft(owner, key["bot_id"])
        yield owner, bot, source


def message(source: dict[str, Any], revision: int = 1, mid: str = "msg_first") -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "message_id": mid,
        "channel_id": source["channel_id"],
        "resource_id": "item_one",
        "source_revision": revision,
        "occurred_at": "2026-10-22T00:00:00Z",
        "kind": "text",
        "payload": {"title": "Synthetic news", "body": "Local pilot"},
    }


def counts(settings: Settings) -> dict[str, int]:
    with Database(settings).transaction() as connection:
        row = connection.execute(
            "SELECT (SELECT count(*) FROM source_records) AS records, "
            "(SELECT count(*) FROM message_receipts) AS receipts, "
            "(SELECT count(*) FROM ingest_history) AS history, "
            "(SELECT count(*) FROM change_outbox) AS outbox"
        ).fetchone()
        assert row is not None
        return row


def test_retry_fingerprint_and_persistent_receipt(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    body = message(source)
    first = bot.post("/v1/bot/messages", json=body)
    assert first.status_code == 200 and first.json()["data_revision"] == 1
    assert (
        datetime.fromisoformat(first.json()["received_at"]).utcoffset()
        == datetime.now(UTC).utcoffset()
    )
    reordered = json.dumps(dict(reversed(list(body.items()))), indent=4)
    replay = bot.post(
        "/v1/bot/messages", content=reordered, headers={"Content-Type": "application/json"}
    )
    assert replay.json() == first.json()
    changed = deepcopy(body)
    changed["payload"]["body"] = "Changed"
    assert bot.post("/v1/bot/messages", json=changed).json()["code"] == "idempotency_conflict"
    numeric = {**body, "source_revision": 1.0}
    assert bot.post("/v1/bot/messages", json=numeric).json()["code"] == "idempotency_conflict"
    second_source = draft(owner, source["bot_id"], "another-channel")
    assert (
        bot.post(
            "/v1/bot/messages", json={**body, "channel_id": second_source["channel_id"]}
        ).json()["code"]
        == "idempotency_conflict"
    )
    with client(settings) as restarted:
        restarted.headers.update({"Authorization": bot.headers["Authorization"]})
        assert restarted.post("/v1/bot/messages", json=body).json() == first.json()
    assert counts(settings) == {"records": 1, "receipts": 1, "history": 1, "outbox": 1}


def test_delete_stale_and_recreation(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    _, bot, source = gateway
    assert bot.post("/v1/bot/messages", json=message(source)).status_code == 200
    deleted = message(source, 2, "msg_delete")
    deleted.pop("payload")
    deleted["kind"] = "delete"
    assert bot.post("/v1/bot/messages", json=deleted).json()["data_revision"] == 2
    assert (
        bot.post("/v1/bot/messages", json=message(source, 1, "late")).json()["code"]
        == "stale_source_revision"
    )
    event = {k: v for k, v in message(source).items() if k not in {"payload", "source_revision"}}
    event.update(kind="event", event_name="news.published", message_id="hint")
    assert bot.post("/v1/bot/messages", json=event).status_code == 404
    with Database(settings).transaction() as connection:
        row = connection.execute("SELECT * FROM source_records").fetchone()
        assert row and row["deleted"] and row["content"] is None and row["source_revision"] == 2
    recreated = message(source, 3, "newer")
    recreated["occurred_at"] = "2000-01-01T00:00:00Z"
    assert bot.post("/v1/bot/messages", json=recreated).json()["data_revision"] == 3
    assert bot.post("/v1/bot/messages", json=event).json()["data_revision"] == 4
    with Database(settings).transaction() as connection:
        row = connection.execute("SELECT * FROM source_records").fetchone()
        assert (
            row and not row["deleted"] and row["source_revision"] == 3 and row["data_revision"] == 3
        )


def test_product_chart_and_validation_bounds(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    _, bot, source = gateway
    product = {
        **message(source),
        "kind": "data",
        "content_type": "product",
        "payload": {
            "title": "Notebook",
            "description": "Synthetic",
            "price": {"amount_minor": 990, "currency": "EUR"},
            "availability": "in_stock",
        },
    }
    assert bot.post("/v1/bot/messages", json=product).status_code == 200
    chart = {
        **message(source, 2, "chart"),
        "kind": "data",
        "content_type": "chart",
        "payload": {
            "title": "Sales",
            "x_label": "Day",
            "x_kind": "number",
            "y_label": "Count",
            "unit": "items",
            "series": [{"name": "Sales", "points": [{"x": 1, "y": 10}, {"x": 2, "y": 15}]}],
        },
    }
    assert bot.post("/v1/bot/messages", json=chart).status_code == 200
    invalid: list[dict[str, Any]] = []
    invalid.append({**message(source), "schema_version": "2.0"})
    invalid.append({**message(source), "bot_id": "forged"})
    invalid.append({**message(source), "source_revision": True})
    invalid.append({**message(source), "payload": {"title": "Long", "body": "x" * 20001}})
    for text in ("\x00", "\ud800"):
        invalid.append({**message(source), "payload": {"title": text, "body": ""}})
    bad_currency = deepcopy(product)
    bad_currency["payload"]["price"]["currency"] = "XXX"
    invalid.append(bad_currency)
    negative = deepcopy(product)
    negative["payload"]["price"]["amount_minor"] = -1
    invalid.append(negative)
    bad_chart = deepcopy(chart)
    bad_chart["payload"]["series"][0]["points"].reverse()
    invalid.append(bad_chart)
    duplicate = deepcopy(chart)
    duplicate["payload"]["series"] *= 2
    invalid.append(duplicate)
    oversized = deepcopy(chart)
    oversized["payload"]["series"][0]["points"] = [{"x": x, "y": 1} for x in range(1001)]
    invalid.append(oversized)
    for body in invalid:
        response = bot.post(
            "/v1/bot/messages",
            content=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
    response = bot.post(
        "/v1/bot/messages", content=" " * 262145, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert counts(settings) == {"records": 1, "receipts": 2, "history": 2, "outbox": 2}


def test_bot_ownership_scopes_and_revoke_before_replay(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    body = message(source)
    assert bot.post("/v1/bot/messages", json=body).status_code == 200
    second = create_bot(owner, "Other bot")
    key = exchange(owner, second["registration_credential"])
    foreign_source = draft(owner, key["bot_id"], "other-bot-channel")
    assert (
        bot.post(
            "/v1/bot/messages", json={**body, "channel_id": foreign_source["channel_id"]}
        ).status_code
        == 404
    )
    assert bot.post("/v1/bot/messages", json=body, headers=auth(key["api_key"])).status_code == 404
    own_second = message(foreign_source)
    assert (
        bot.post("/v1/bot/messages", json=own_second, headers=auth(key["api_key"])).status_code
        == 200
    )
    readonly = owner.post(
        "/v1/bots/" + source["bot_id"] + "/keys", json={"scopes": ["events:read"]}
    ).json()["api_key"]
    assert bot.post("/v1/bot/messages", json=body, headers=auth(readonly)).status_code == 403
    assert owner.post("/v1/bot/messages", json=body).status_code == 401
    assert owner.delete("/v1/bots/" + source["bot_id"]).status_code == 204
    assert bot.post("/v1/bot/messages", json=body).status_code == 401


def test_concurrent_duplicate_and_ordered_updates(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    _, bot, source = gateway
    authorization = bot.headers["Authorization"]

    def send(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        with client(settings) as http:
            response = http.post(
                "/v1/bot/messages", json=body, headers={"Authorization": authorization}
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=4) as executor:
        duplicates = list(executor.map(send, [message(source)] * 4))
        assert all(item == duplicates[0] for item in duplicates) and duplicates[0][0] == 200
        updates = list(
            executor.map(send, [message(source, 2, "second"), message(source, 3, "third")])
        )
    assert updates[1][0] == 200 and updates[0][0] in (200, 409)
    with Database(settings).transaction() as connection:
        row = connection.execute("SELECT source_revision FROM source_records").fetchone()
        assert row == {"source_revision": 3}
    totals = counts(settings)
    assert totals["receipts"] == totals["history"] == totals["outbox"] == 2 + (updates[0][0] == 200)


def test_outbox_failure_rolls_back_entire_message(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    _, bot, source = gateway
    database = Database(settings)
    with database.transaction() as connection:
        connection.execute(
            "CREATE FUNCTION fail_outbox() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN RAISE EXCEPTION 'synthetic storage failure'; END $$"
        )
        connection.execute(
            "CREATE TRIGGER fail_outbox BEFORE INSERT ON change_outbox "
            "FOR EACH ROW EXECUTE FUNCTION fail_outbox()"
        )
    response = bot.post("/v1/bot/messages", json=message(source))
    assert response.status_code == 500 and "synthetic storage failure" not in response.text
    assert counts(settings) == {"records": 0, "receipts": 0, "history": 0, "outbox": 0}
    with database.transaction() as connection:
        assert connection.execute("SELECT data_revision FROM channel_content").fetchone() == {
            "data_revision": 0
        }
        connection.execute("DROP TRIGGER fail_outbox ON change_outbox")
        connection.execute("DROP FUNCTION fail_outbox()")
    assert bot.post("/v1/bot/messages", json=message(source)).json()["data_revision"] == 1


def test_bounded_retention_preserves_latest_and_dedup(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    _, bot, source = gateway
    body = message(source)
    original = bot.post("/v1/bot/messages", json=body).json()
    database = Database(settings)
    with database.transaction() as connection:
        connection.execute("UPDATE ingest_history SET received_at=now()-interval '8 days'")
    assert prune(database) == {"history": 1, "receipts": 0}
    assert bot.post("/v1/bot/messages", json=body).json() == original
    assert counts(settings) == {"records": 1, "receipts": 1, "history": 0, "outbox": 1}
    with database.transaction() as connection:
        connection.execute("UPDATE message_receipts SET received_at=now()-interval '31 days'")
    assert prune(database) == {"history": 0, "receipts": 1}
    assert bot.post("/v1/bot/messages", json=body).json()["code"] == "stale_source_revision"
    assert bot.post("/v1/bot/messages", json=message(source, 2)).json()["data_revision"] == 2


def test_ingestion_buckets_are_durable_and_global(settings: Settings) -> None:
    settings = settings.model_copy(
        update={"ingest_bot_per_minute": 2, "ingest_total_per_minute": 3}
    )
    with client(settings) as owner, client(settings) as bot:
        register(owner, "alice")
        business(owner)
        first = create_bot(owner)
        first_key = exchange(bot, first["registration_credential"])
        second = create_bot(owner)
        second_key = exchange(bot, second["registration_credential"])
        source = draft(owner, first_key["bot_id"])
        other = draft(owner, second_key["bot_id"], "second-bot")
        for body in (message(source), message(source, 2, "two")):
            assert (
                bot.post(
                    "/v1/bot/messages", json=body, headers=auth(first_key["api_key"])
                ).status_code
                == 200
            )
        rejected = bot.post(
            "/v1/bot/messages", json=message(source, 3, "three"), headers=auth(first_key["api_key"])
        )
        assert rejected.status_code == 429 and int(rejected.headers["retry-after"]) > 0
        assert (
            bot.post(
                "/v1/bot/messages", json=message(other), headers=auth(second_key["api_key"])
            ).status_code
            == 200
        )
    with client(settings) as restarted:
        assert (
            restarted.post(
                "/v1/bot/messages",
                json=message(other, 2, "two"),
                headers=auth(second_key["api_key"]),
            ).status_code
            == 429
        )
        with Database(settings).transaction() as connection:
            connection.execute("UPDATE rate_buckets SET updated_at=now()-interval '1 minute'")
        assert (
            restarted.post(
                "/v1/bot/messages",
                json=message(other, 2, "two"),
                headers=auth(second_key["api_key"]),
            ).status_code
            == 200
        )


def test_draft_ownership_slug_conflict_and_no_consumer_route(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, _, source = gateway
    with client(settings) as bob:
        register(bob, "bob")
        business(bob)
        body = {k: source[k] for k in ("bot_id", "slug", "title", "visibility")}
        assert bob.post("/v1/channels", json=body).status_code == 404
        assert owner.post("/v1/channels", json=body).status_code == 409
        assert owner.post("/v1/channels", json={**body, "published": True}).status_code == 422
        assert bob.get("/v1/channels/" + source["channel_id"]).status_code == 404
    with Database(settings).transaction() as connection:
        assert connection.execute("SELECT count(*) AS count FROM channel_access").fetchone() == {
            "count": 1
        }
