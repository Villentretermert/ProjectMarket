"""Real limits, rollback, retention/resync and operational alarms; synthetic payloads only."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.maintenance import maintain, prune, prune_updates
from marketob_api.observability import ObservationMiddleware, SafeFormatter
from marketob_api.transport import ProtocolMiddleware
from marketob_api.updates import dispatch

from scripts.operations import alerts, log_metrics, snapshot
from tests.test_actions import action_body, event_path, queue, report
from tests.test_actions import shop as shop
from tests.test_bots import auth, create_bot, exchange
from tests.test_favorites import ready
from tests.test_identity import settings as settings
from tests.test_ingestion import counts, draft, message
from tests.test_ingestion import gateway as gateway
from tests.test_updates import poll


def test_log_allowlist_and_exception_redaction(caplog: pytest.LogCaptureFixture) -> None:
    app = FastAPI()
    app.add_middleware(ProtocolMiddleware)
    app.add_middleware(ObservationMiddleware)

    @app.get("/v1/test/{identifier}")
    def broken(identifier: str) -> None:
        raise RuntimeError("SECRET_DATABASE_PASSWORD " + identifier)

    with caplog.at_level(logging.INFO, logger="marketob.operations"):
        with TestClient(app) as http:
            response = http.get(
                "/v1/test/PRIVATE_NAME?token=SECRET_QUERY",
                headers={"Authorization": "Bearer SECRET_KEY"},
            )
    assert response.status_code == 500
    records = [r for r in caplog.records if r.name == "marketob.operations"]
    serialized = SafeFormatter().format(records[-1])
    assert "SECRET" not in serialized and "PRIVATE_NAME" not in serialized
    value = json.loads(serialized)
    assert value["route"] == "/v1/test/{identifier}"
    assert value["request_id"] == response.headers["x-request-id"]
    assert value["status"] == 500 and value["duration_ms"] > 0
    hostile = logging.LogRecord(
        "uvicorn.error", logging.ERROR, "", 1, "SECRET %s", ("PASSWORD",), None
    )
    assert "SECRET" not in SafeFormatter().format(hostile)


def test_log_metrics_and_alert_window(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    rows: list[dict[str, Any]] = [
        {"time": (now - timedelta(seconds=1)).isoformat(), "event": "runtime"}
    ]
    rows += [
        {
            "time": now.isoformat(),
            "event": "http",
            "method": "POST",
            "route": "/v1/bot/messages",
            "duration_ms": n,
            "status": 200 if n < 99 else 503,
        }
        for n in range(100)
    ]
    (tmp_path / "api.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    metrics = log_metrics(tmp_path, now.isoformat(), now.isoformat())
    assert metrics["window_complete"] and metrics["unexpected_5xx_fraction"] == 0.01
    assert metrics["routes"]["POST /v1/bot/messages"]["p95_ms"] == 94


@pytest.mark.integration
def test_history_capacity_rollback_replay_and_noisy_bot_isolation(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    original = bot.post("/v1/bot/messages", json=message(source)).json()
    database = Database(settings)
    with database.transaction() as conn:
        usage = conn.execute("SELECT * FROM history_usage").fetchone()
        assert usage and usage["rows"] == 1 and usage["bytes"] > 0
        # Inject the capacity boundary without writing 256 MiB into a unit test fixture.
        conn.execute("UPDATE history_usage SET bytes=268435456")
    before = counts(settings)
    blocked = bot.post("/v1/bot/messages", json=message(source, 2, "second"))
    assert blocked.status_code == 429 and blocked.headers["retry-after"] == "60"
    assert counts(settings) == before
    assert bot.post("/v1/bot/messages", json=message(source)).json() == original
    other_key = exchange(bot, create_bot(owner)["registration_credential"])
    other = draft(owner, other_key["bot_id"], "healthy-bot")
    assert (
        bot.post(
            "/v1/bot/messages", json=message(other), headers=auth(other_key["api_key"])
        ).status_code
        == 200
    )
    # Exercise real noisy-bot quota; rejected attempts must not consume aggregate tokens.
    with database.transaction() as conn:
        conn.execute(
            "UPDATE rate_buckets SET tokens=0,updated_at=now() WHERE bucket=%s",
            ("ingest:bot:" + source["bot_id"],),
        )
    for n in range(8):
        assert (
            bot.post("/v1/bot/messages", json=message(source, n + 2, "noise_" + str(n))).status_code
            == 429
        )
    assert (
        bot.post(
            "/v1/bot/messages",
            json=message(other, 2, "healthy_second"),
            headers=auth(other_key["api_key"]),
        ).status_code
        == 200
    )
    with database.transaction() as conn:
        conn.execute(
            "UPDATE history_usage SET bytes=%s WHERE bot_id=%s", (usage["bytes"], source["bot_id"])
        )
        conn.execute(
            "UPDATE ingest_history SET received_at=now()-interval '31 days' WHERE bot_id=%s",
            (source["bot_id"],),
        )
    assert prune(database)["history"] == 1
    with database.transaction() as conn:
        row = conn.execute(
            "SELECT rows,bytes FROM history_usage WHERE bot_id=%s", (source["bot_id"],)
        ).fetchone()
        assert row == {"rows": 0, "bytes": 0}


@pytest.mark.integration
def test_outbox_retention_resync_and_worker_alert(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source)
    database = Database(settings)
    cursor = poll(owner)["next_cursor"]
    assert bot.post("/v1/bot/messages", json=message(source, 2, "new")).status_code == 200
    poll(owner, cursor)
    assert "worker_stale" in alerts(snapshot(database))
    with database.transaction() as conn:
        conn.execute("UPDATE change_outbox SET delivered_at=now()-interval '2 hours'")
    assert prune_updates(database) > 0
    expired = owner.get("/v1/updates", params={"cursor": cursor})
    assert expired.status_code == 410 and expired.json()["code"] == "resync_required"
    fresh = poll(owner)["next_cursor"]
    assert bot.post("/v1/bot/messages", json=message(source, 3, "after_prune")).status_code == 200
    assert poll(owner, fresh, source["channel_id"])["items"][0]["revision"] == 3
    maintain(database)
    assert alerts(snapshot(database)) == []


@pytest.mark.integration
def test_outbox_backpressure_preserves_acknowledged_data_and_recovers(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    _, bot, source = gateway
    original = bot.post("/v1/bot/messages", json=message(source)).json()
    database = Database(settings)
    with database.transaction() as conn:
        # Bulk fixture reaches the actual admission limit without 20,000 HTTP calls.
        conn.execute("SET LOCAL statement_timeout='30s'")
        conn.execute("ALTER TABLE change_outbox DISABLE TRIGGER outbox_admission")
        conn.execute(
            "INSERT INTO change_outbox(channel_id,kind) "
            "SELECT %s,'channel.changed' FROM generate_series(1,19999)",
            (source["channel_id"],),
        )
        conn.execute("ALTER TABLE change_outbox ENABLE TRIGGER outbox_admission")
    assert snapshot(database)["outbox_pending"] == 20000
    blocked = bot.post("/v1/bot/messages", json=message(source, 2, "retry_after_capacity"))
    assert blocked.status_code == 429 and blocked.headers["retry-after"] == "60"
    assert counts(settings)["receipts"] == 1
    assert bot.post("/v1/bot/messages", json=message(source)).json() == original
    assert "outbox_capacity" in alerts(snapshot(database))
    dispatch(database)
    assert (
        bot.post("/v1/bot/messages", json=message(source, 2, "retry_after_capacity")).status_code
        == 200
    )


@pytest.mark.integration
def test_bot_queue_bound_is_serialized_replayable_and_recoverable(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    _, bot, customer, source, user_id = shop
    first = queue(customer, source)
    database = Database(settings)
    with database.transaction() as conn:
        conn.execute(
            "INSERT INTO action_requests(action_request_id,event_id,channel_id,bot_id,user_id,"
            "actor_ref,resource_id,action_id,observed_source_revision,quantity,idempotency_key,"
            "body_hash) SELECT 'seed_request_'||n,'seed_event_'||n,channel_id,bot_id,user_id,"
            "actor_ref,resource_id,action_id,1,1,'seed_key_'||n,body_hash "
            "FROM action_requests CROSS JOIN generate_series(1,998) n "
            "WHERE action_request_id=%s",
            (first["action_request_id"],),
        )
    route = "/v1/channels/" + source["channel_id"] + "/actions"

    def submit(n: int) -> int:
        return int(
            customer.post(
                route, json=action_body(), headers={"Idempotency-Key": "capacity_" + str(n)}
            ).status_code
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, (1, 2))) == [202, 429]
    assert queue(customer, source) == first
    assert snapshot(database)["unresolved"] == 1000
    assert "bot_queue_capacity" in alerts(snapshot(database))
    event = bot.get("/v1/bot/events").json()["items"][0]
    assert bot.post(event_path(event, "ack"), json={}).status_code == 200
    assert bot.post(event_path(event, "result"), json=report()).status_code == 200
    assert submit(3) == 202
    with database.transaction() as conn:
        conn.execute(
            "UPDATE action_requests SET created_at=now()-interval '2 minutes' "
            "WHERE terminal_at IS NULL"
        )
    maintain(database)
    gauges = snapshot(database)
    assert gauges["unknown"] == 1000 and gauges["unresolved"] == 1000
    assert "requests_need_reconciliation" in alerts(gauges)


@pytest.mark.integration
def test_worker_recovers_full_outbox_before_creating_timeout_notifications(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    _, _, customer, source, _ = shop
    queue(customer, source)
    database = Database(settings)
    with database.transaction() as conn:
        conn.execute("SET LOCAL statement_timeout='30s'")
        conn.execute("UPDATE action_requests SET created_at=now()-interval '2 minutes'")
        count = conn.execute("SELECT count(*) n FROM change_outbox").fetchone()
        assert count is not None
        conn.execute("ALTER TABLE change_outbox DISABLE TRIGGER outbox_admission")
        conn.execute(
            "INSERT INTO change_outbox(channel_id,kind) SELECT %s,'channel.changed' "
            "FROM generate_series(1,%s)",
            (source["channel_id"], 20000 - count["n"]),
        )
        conn.execute("ALTER TABLE change_outbox ENABLE TRIGGER outbox_admission")
    assert snapshot(database)["outbox_pending"] == 20000
    result = maintain(database)
    assert result["unknown"] == 1
    state = snapshot(database)
    assert state["outbox_pending"] == 15001
    assert "worker_stale" not in alerts(state)
