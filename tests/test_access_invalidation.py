"""Permission commits must not depend on shared notification queue capacity."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.maintenance import prune_updates

from tests.test_actions import event_path, queue
from tests.test_actions import shop as shop
from tests.test_channels import path, publish
from tests.test_favorites import ready
from tests.test_identity import PASSWORD, client, register
from tests.test_identity import settings as settings
from tests.test_ingestion import draft, message
from tests.test_ingestion import gateway as gateway
from tests.test_teams import add
from tests.test_updates import poll

pytestmark = pytest.mark.integration


def fill_queue(database: Database, channel_id: str, *, total: bool = False) -> int:
    """Seed only the fixture's disposable schema; restore admission before HTTP calls."""
    with database.transaction() as connection:
        connection.execute("SET LOCAL statement_timeout='30s'")
        state = connection.execute("SELECT watermark FROM delivery_state FOR UPDATE").fetchone()
        assert state
        count = connection.execute(
            "SELECT count(*) n FROM change_outbox"
            + ("" if total else " WHERE delivery_sequence IS NULL")
        ).fetchone()
        assert count
        amount = (250000 if total else 20000) - count["n"]
        connection.execute("ALTER TABLE change_outbox DISABLE TRIGGER outbox_admission")
        connection.execute(
            "INSERT INTO change_outbox(channel_id,kind,delivery_sequence,delivered_at) "
            "SELECT %s,'channel.changed',CASE WHEN %s THEN %s+n END, "
            "CASE WHEN %s THEN now() END FROM generate_series(1,%s) n",
            (channel_id, total, state["watermark"], total, amount),
        )
        connection.execute("ALTER TABLE change_outbox ENABLE TRIGGER outbox_admission")
        if total:
            connection.execute("UPDATE delivery_state SET watermark=watermark+%s", (amount,))
        row = connection.execute("SELECT count(*) n FROM change_outbox").fetchone()
        assert row
        return int(row["n"])


def expect_resync(http: TestClient, cursor: str) -> None:
    response = http.get("/v1/updates", params={"cursor": cursor})
    assert response.status_code == 410, response.text
    assert response.json()["code"] == "resync_required"


def set_visibility(owner: TestClient, source: dict[str, Any], visibility: str) -> int:
    current = owner.get(path(source)).json()
    version = current["layout"]["template_version"]
    value = {key: current[key] for key in ("title", "layout", "actions")}
    value.update(visibility=visibility, expected_template_version=version)
    value["layout"]["template_version"] = version + 1
    result = owner.put(path(source), json=value)
    assert result.status_code == 200, result.text
    return int(version) + 1


@pytest.mark.parametrize(
    "operation",
    ["grant", "member", "demote", "reader", "bot", "channel", "publish", "rollback"],
)
def test_permission_changes_commit_with_full_pending_queue(
    settings: Settings, shop: tuple[Any, ...], operation: str
) -> None:
    owner, bot, reader, source, uid = shop
    database = Database(settings)
    org = owner.get("/v1/account/business-profile").json()["org_id"]
    if operation in {"member", "demote"}:
        add(owner, org, "customer", "admin")
        assert owner.delete(path(source, "/grants/" + uid)).status_code == 204
    if operation in {"publish", "rollback"}:
        publish(owner, source, set_visibility(owner, source, "public"))
        assert owner.delete(path(source, "/grants/" + uid)).status_code == 204
        version = set_visibility(owner, source, "selected")
    pending = queue(reader, source)
    acknowledged = queue(reader, source, "acked_request")
    event = next(
        item
        for item in bot.get("/v1/bot/events").json()["items"]
        if item["action_request_id"] == acknowledged["action_request_id"]
    )
    assert bot.post(event_path(event, "ack"), json={}).status_code == 200
    cursor = poll(reader)["next_cursor"]
    before = fill_queue(database, source["channel_id"])
    with database.transaction() as connection:
        marker_before = connection.execute("SELECT watermark FROM delivery_state").fetchone()
        assert marker_before
    if operation == "grant":
        result = owner.delete(path(source, "/grants/" + uid))
    elif operation == "member":
        result = owner.delete(f"/v1/workspaces/{org}/members/{uid}")
    elif operation == "demote":
        result = owner.put(
            f"/v1/workspaces/{org}/members", json={"username": "customer", "role": "editor"}
        )
    elif operation == "reader":
        result = reader.request(
            "DELETE", "/v1/account", json={"password": PASSWORD, "confirmation": "DELETE"}
        )
    elif operation == "bot":
        result = owner.delete("/v1/bots/" + source["bot_id"])
    elif operation == "channel":
        result = owner.delete(path(source))
    elif operation == "publish":
        result = owner.post(path(source, "/publish"), json={"expected_template_version": version})
    else:
        result = owner.post(
            path(source, "/rollback"),
            json={"expected_template_version": version, "target_template_version": 2},
        )
    assert result.status_code in {200, 204}, result.text
    with database.transaction() as connection:
        assert connection.execute(
            "SELECT watermark,retention_floor FROM delivery_state"
        ).fetchone() == {
            "watermark": marker_before["watermark"] + 1,
            "retention_floor": marker_before["watermark"] + 1,
        }
        assert connection.execute("SELECT count(*) n FROM change_outbox").fetchone() == {
            "n": before - (2 if operation == "reader" else 0)
        }
        states = connection.execute(
            "SELECT action_request_id,state FROM action_requests"
        ).fetchall()
        by_id = {row["action_request_id"]: row["state"] for row in states}
        assert by_id[acknowledged["action_request_id"]] == (
            "queued" if operation == "demote" else "unknown"
        )
        expected = (
            "queued"
            if operation == "demote"
            else "unknown"
            if operation in {"owner", "bot", "channel"}
            else "cancelled"
        )
        assert by_id[pending["action_request_id"]] == expected
        assert connection.execute("SELECT count(*) n FROM message_receipts").fetchone() == {"n": 1}
    if operation == "reader":
        assert reader.get("/v1/updates", params={"cursor": cursor}).status_code == 401
    else:
        expect_resync(reader, cursor)
        response = reader.get("/v1/channels/" + source["slug"])
        assert response.status_code == (200 if operation == "demote" else 404)
        if operation == "demote":
            assert reader.get("/v1/bots/" + source["bot_id"] + "/keys").status_code == 403
    if operation in {"owner", "bot"}:
        assert bot.get("/v1/bot/identity").status_code == 401


@pytest.mark.parametrize("total", [False, True], ids=["pending-cap", "total-cap"])
def test_queue_owned_by_another_workspace_cannot_block_revoke(
    settings: Settings, shop: tuple[Any, ...], total: bool
) -> None:
    owner, bot, reader, source, uid = shop
    database = Database(settings)
    with client(settings) as other:
        register(other, "independent_owner")
        # Independent workspace and bot/channel use the same global queue.
        assert other.put("/v1/account/business-profile", json={"name": "Other"}).status_code == 200
        reg = other.post("/v1/bots", json={"name": "Other bot"}).json()
        unrelated = draft(other, reg["bot"]["bot_id"], "other-source")
        cursor = poll(reader)["next_cursor"]
        count = fill_queue(database, unrelated["channel_id"], total=total)
        assert (
            bot.post("/v1/bot/messages", json=message(source, 2, "capacity-control")).status_code
            == 429
        )
        assert owner.delete(path(source, "/grants/" + uid)).status_code == 204
        expect_resync(reader, cursor)
        assert reader.get("/v1/channels/" + source["slug"]).status_code == 404
        with database.transaction() as connection:
            assert connection.execute("SELECT count(*) n FROM change_outbox").fetchone() == {
                "n": count
            }
        # Ordinary data backpressure remains intact (the pending case may be dispatched by GET).
        if total:
            assert (
                bot.post(
                    "/v1/bot/messages", json=message(source, 2, "capacity-control")
                ).status_code
                == 429
            )


def test_failed_marker_rolls_back_grant_and_request_reconciliation(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, _, reader, source, uid = shop
    pending = queue(reader, source)
    database = Database(settings)
    cursor = poll(reader)["next_cursor"]
    with database.transaction() as connection:
        before = connection.execute("SELECT * FROM delivery_state").fetchone()
        connection.execute(
            "CREATE FUNCTION reject_marker() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN RAISE EXCEPTION 'synthetic'; END $$"
        )
        connection.execute(
            "CREATE TRIGGER marker_fault BEFORE UPDATE ON delivery_state "
            "FOR EACH ROW EXECUTE FUNCTION reject_marker()"
        )
    assert owner.delete(path(source, "/grants/" + uid)).status_code == 500
    with database.transaction() as connection:
        assert connection.execute("SELECT * FROM delivery_state").fetchone() == before
        assert connection.execute(
            "SELECT state FROM action_requests WHERE action_request_id=%s",
            (pending["action_request_id"],),
        ).fetchone() == {"state": "queued"}
        connection.execute("DROP TRIGGER marker_fault ON delivery_state")
    assert reader.get("/v1/channels/" + source["slug"]).status_code == 200
    assert poll(reader, cursor)["items"] == []
    assert owner.delete(path(source, "/grants/" + uid)).status_code == 204
    expect_resync(reader, cursor)


def test_late_commit_and_retention_cannot_reuse_or_lower_permission_marker(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, bot, _, source, uid = shop
    other = draft(owner, source["bot_id"], "late-independent-source")
    ready(owner, bot, other)
    database = Database(settings)
    stale = poll(owner)["next_cursor"]
    with database.transaction() as delayed:
        delayed.execute(
            "INSERT INTO change_outbox(channel_id,kind,data_revision) "
            "VALUES (%s,'channel.changed',17)",
            (other["channel_id"],),
        )
        assert owner.delete(path(source, "/grants/" + uid)).status_code == 204
        expect_resync(owner, stale)
        fresh = poll(owner)["next_cursor"]
        with database.transaction() as connection:
            marker = connection.execute("SELECT watermark FROM delivery_state").fetchone()
            assert marker
            connection.execute(
                "UPDATE change_outbox SET delivered_at=now()-interval '2 hours' "
                "WHERE delivery_sequence IS NOT NULL"
            )
        assert prune_updates(database) > 0
        with database.transaction() as connection:
            assert connection.execute("SELECT retention_floor FROM delivery_state").fetchone() == {
                "retention_floor": marker["watermark"]
            }
        expect_resync(owner, stale)
        assert poll(owner, fresh)["items"] == []
    page = poll(owner, fresh, other["channel_id"])
    assert [item["revision"] for item in page["items"]] == [17]
    assert int(page["items"][0]["update_id"].split("_")[1]) > marker["watermark"]
    with database.transaction() as connection:
        assert connection.execute("SELECT count(*) n FROM message_receipts").fetchone() == {"n": 2}


def test_noops_and_denied_changes_do_not_invalidate_but_multichannel_changes_do_once(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, _, reader, source, uid = shop
    org = owner.get("/v1/account/business-profile").json()["org_id"]
    for n in range(4):
        draft(owner, source["bot_id"], f"extra-{n}")
    add(owner, org, "customer", "editor")
    database = Database(settings)
    cursor = poll(reader)["next_cursor"]
    before = fill_queue(database, source["channel_id"])
    with database.transaction() as connection:
        state = connection.execute("SELECT * FROM delivery_state").fetchone()
        assert state
    assert owner.put(path(source, "/grants/" + uid), json={}).status_code == 204
    add(owner, org, "customer", "editor")
    assert owner.delete(path(source, "/grants/nonexistent_user")).status_code == 204
    assert reader.delete(path(source, "/grants/" + uid)).status_code == 403
    assert (
        owner.post(path(source, "/publish"), json={"expected_template_version": 999}).status_code
        == 409
    )
    with database.transaction() as connection:
        assert connection.execute("SELECT * FROM delivery_state").fetchone() == state
    assert owner.delete(f"/v1/workspaces/{org}/members/{uid}").status_code == 204
    with database.transaction() as connection:
        assert connection.execute("SELECT watermark FROM delivery_state").fetchone() == {
            "watermark": state["watermark"] + 1
        }
        assert connection.execute("SELECT count(*) n FROM change_outbox").fetchone() == {
            "n": before
        }
    # An explicit read grant survives team removal; restoring it is also capacity-independent.
    assert reader.get("/v1/channels/" + source["slug"]).status_code == 200
    assert owner.delete(path(source, "/grants/" + uid)).status_code == 204
    assert owner.put(path(source, "/grants/" + uid), json={}).status_code == 204
    with database.transaction() as connection:
        assert connection.execute(
            "SELECT count(*) n FROM change_outbox WHERE delivery_sequence IS NULL"
        ).fetchone() == {"n": 20000}
    expect_resync(reader, cursor)
    assert reader.get("/v1/channels/" + source["slug"]).status_code == 200
