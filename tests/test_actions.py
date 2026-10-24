"""Real PostgreSQL action delivery, recovery, race and authorization acceptance."""

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.request_state import maintain_requests

from tests.test_bots import auth, create_bot, exchange
from tests.test_channels import edit, path, publish, validate
from tests.test_identity import PASSWORD, client, register
from tests.test_identity import settings as settings
from tests.test_ingestion import gateway as gateway
from tests.test_ingestion import message

pytestmark = pytest.mark.integration


def catalog(
    owner: TestClient, bot: TestClient, source: dict[str, Any], visibility: str = "selected"
) -> None:
    payload = message(source)
    payload.update(
        kind="data",
        content_type="product",
        payload={
            "title": "Soap",
            "description": "Synthetic daily item",
            "price": {"amount_minor": 200, "currency": "EUR"},
            "availability": "in_stock",
        },
    )
    assert bot.post("/v1/bot/messages", json=payload).status_code == 200
    body = edit(source, visibility=visibility)
    body["layout"]["blocks"][0].update(content_type="product", view="card", action_ids=["purchase"])
    body["actions"] = [
        {
            "action_id": "purchase",
            "resource_id": "item_one",
            "kind": "request_purchase",
            "label": "Request purchase",
        }
    ]
    assert owner.put(path(source), json=body).status_code == 200
    publish(owner, source)


@pytest.fixture
def shop(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> Iterator[tuple[TestClient, TestClient, TestClient, dict[str, Any], str]]:
    owner, bot, source = gateway
    catalog(owner, bot, source)
    with client(settings) as customer:
        user_id = register(customer, "customer")
        assert owner.put(path(source, "/grants/" + user_id), json={}).status_code == 204
        yield owner, bot, customer, source, user_id


def action_body() -> dict[str, Any]:
    return {
        "action_id": "purchase",
        "resource_id": "item_one",
        "observed_source_revision": 1,
        "quantity": 1,
    }


def queue(
    customer: TestClient, source: dict[str, Any], key: str = "purchase_one"
) -> dict[str, Any]:
    response = customer.post(
        "/v1/channels/" + source["channel_id"] + "/actions",
        json=action_body(),
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    validate("ActionRequest", response.json())
    return dict(response.json())


def report(state: str = "confirmed", revision: int = 1, rid: str = "result_one") -> dict[str, Any]:
    return {
        "result_id": rid,
        "result_revision": revision,
        "state": state,
        "summary": "Synthetic result; no payment.",
    }


def event_path(event: dict[str, Any], operation: str) -> str:
    return "/v1/bot/events/" + str(event["event_id"]) + "/" + operation


def test_durable_delivery_ack_result_and_idempotent_replay(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    _, bot, customer, source, user_id = shop
    request = queue(customer, source)
    assert request["state"] == "queued" and queue(customer, source) == request
    page = bot.get("/v1/bot/events").json()
    validate("EventPage", page)
    event = page["items"][0]
    assert user_id not in str(event) and "customer" not in str(event)
    assert event["actor_ref"].startswith("actor_")
    assert bot.get("/v1/bot/events").json() == page
    assert bot.post(event_path(event, "result"), json=report()).json()["code"] == "ack_required"
    with client(settings) as restarted:
        restarted.headers["Authorization"] = bot.headers["Authorization"]
        assert restarted.get("/v1/bot/events").json() == page
        ack = restarted.post(event_path(event, "ack"), json={})
        validate("Ack", ack.json())
        assert restarted.post(event_path(event, "ack"), json={}).json() == ack.json()
        assert restarted.get("/v1/bot/events").json()["items"] == []
        assert restarted.get("/v1/bot/requests").json()["items"] == [event]
        assert (
            customer.get("/v1/action-requests/" + request["action_request_id"]).json()["state"]
            == "queued"
        )
        progress = report("processing")
        assert (
            restarted.post(event_path(event, "result"), json=progress).json()["state"]
            == "processing"
        )
        terminal = report("confirmed", 2, "result_two")
        final = restarted.post(event_path(event, "result"), json=terminal)
        assert final.status_code == 200 and final.json()["state"] == "confirmed"
        assert restarted.post(event_path(event, "result"), json=terminal).json() == final.json()
        assert restarted.post(event_path(event, "result"), json=progress).json() == final.json()
        assert (
            restarted.post(event_path(event, "result"), json=report("failed", 3, "other")).json()[
                "code"
            ]
            == "terminal_conflict"
        )
        assert (
            restarted.post(
                event_path(event, "result"), json={**terminal, "summary": "Changed"}
            ).json()["code"]
            == "idempotency_conflict"
        )
        assert restarted.get("/v1/bot/requests").json()["items"] == []
        assert queue(customer, source)["state"] == "confirmed"


def test_server_validates_current_item_quantity_action_and_body(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, bot, customer, source, _ = shop
    url = "/v1/channels/" + source["channel_id"] + "/actions"
    headers = {"Idempotency-Key": "request_key"}
    cases: list[tuple[dict[str, Any], int]] = [
        ({"price": 1}, 422),
        ({"quantity": 2}, 422),
        ({"resource_id": "foreign"}, 422),
        ({"observed_source_revision": 2}, 409),
        ({"action_id": "hidden"}, 422),
    ]
    for change, status in cases:
        assert (
            customer.post(url, json={**action_body(), **change}, headers=headers).status_code
            == status
        )
    assert customer.post(url, json=action_body()).status_code == 422
    first = queue(customer, source, "request_key")
    assert (
        customer.post(
            url, json={**action_body(), "observed_source_revision": 2}, headers=headers
        ).json()["code"]
        == "idempotency_conflict"
    )
    product = message(source, 2, "out_of_stock")
    product.update(
        kind="data",
        content_type="product",
        payload={
            "title": "Soap",
            "description": "Synthetic",
            "price": {"amount_minor": 200, "currency": "EUR"},
            "availability": "out_of_stock",
        },
    )
    bot.post("/v1/bot/messages", json=product)
    assert (
        customer.post(
            url,
            json={**action_body(), "observed_source_revision": 2},
            headers={"Idempotency-Key": "new_request"},
        ).json()["code"]
        == "resource_unavailable"
    )
    assert queue(customer, source, "request_key") == first
    current = owner.get(path(source)).json()
    body = {
        "title": current["title"],
        "visibility": "selected",
        "layout": {**current["layout"], "template_version": 3},
        "actions": [],
        "expected_template_version": 2,
    }
    body["layout"]["blocks"][0]["action_ids"] = []
    owner.put(path(source), json=body)
    publish(owner, source, 3)
    assert (
        customer.post(
            url, json=action_body(), headers={"Idempotency-Key": "disabled_action"}
        ).json()["code"]
        == "action_not_allowed"
    )


def test_grant_revoke_cancels_unacked_and_reconciles_acked(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, bot, customer, source, user_id = shop
    first = queue(customer, source)
    second = queue(customer, source, "purchase_two")
    events = bot.get("/v1/bot/events").json()["items"]
    assert bot.post(event_path(events[1], "ack"), json={}).status_code == 200
    assert owner.delete(path(source, "/grants/" + user_id)).status_code == 204
    assert bot.post(event_path(events[0], "ack"), json={}).json()["code"] == "request_cancelled"
    assert bot.get("/v1/bot/events").json()["items"] == []
    assert bot.get("/v1/bot/requests").json()["items"] == [events[1]]
    assert customer.get("/v1/action-requests/" + second["action_request_id"]).status_code == 404
    assert (
        customer.post(
            "/v1/channels/" + source["channel_id"] + "/actions",
            json=action_body(),
            headers={"Idempotency-Key": "purchase_one"},
        ).status_code
        == 404
    )
    assert (
        bot.post(event_path(events[1], "result"), json=report("failed")).json()["state"] == "failed"
    )
    owner.put(path(source, "/grants/" + user_id), json={})
    assert (
        customer.get("/v1/action-requests/" + first["action_request_id"]).json()["state"]
        == "cancelled"
    )
    assert (
        customer.get("/v1/action-requests/" + second["action_request_id"]).json()["state"]
        == "failed"
    )


def test_cross_bot_user_scope_and_revoked_key(settings: Settings, shop: tuple[Any, ...]) -> None:
    owner, bot, customer, source, _ = shop
    request = queue(customer, source)
    event = bot.get("/v1/bot/events").json()["items"][0]
    with client(settings) as another, client(settings) as stranger:
        key = exchange(another, create_bot(owner)["registration_credential"])
        another.headers.update(auth(key["api_key"]))
        assert another.get("/v1/bot/events").json()["items"] == []
        assert another.post(event_path(event, "ack"), json={}).status_code == 404
        assert another.post(event_path(event, "result"), json=report()).status_code == 404
        register(stranger, "stranger")
        assert (
            stranger.get("/v1/action-requests/" + request["action_request_id"]).status_code == 404
        )
        narrow = owner.post(
            "/v1/bots/" + source["bot_id"] + "/keys", json={"scopes": ["messages:write"]}
        ).json()
        assert another.get("/v1/bot/events", headers=auth(narrow["api_key"])).status_code == 403
    assert bot.post(event_path(event, "ack"), json={}).status_code == 200
    identity = bot.get("/v1/bot/identity").json()
    owner.delete("/v1/bots/" + source["bot_id"] + "/keys/" + identity["key_id"])
    assert bot.post(event_path(event, "ack"), json={}).status_code == 401
    assert bot.post(event_path(event, "result"), json=report()).status_code == 401


def test_timeout_and_retention_preserve_unresolved(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    _, bot, customer, source, _ = shop
    queued = queue(customer, source)
    with Database(settings).transaction() as connection:
        connection.execute("UPDATE action_requests SET created_at=now()-interval '61 seconds'")
    assert (
        customer.get("/v1/action-requests/" + queued["action_request_id"]).json()["state"]
        == "unknown"
    )
    assert maintain_requests(Database(settings)) == {"unknown": 1, "requests": 0}
    event = bot.get("/v1/bot/events").json()["items"][0]
    bot.post(event_path(event, "ack"), json={})
    bot.post(event_path(event, "result"), json=report("processing"))
    with Database(settings).transaction() as connection:
        connection.execute("UPDATE action_requests SET progress_at=now()-interval '6 minutes'")
    assert maintain_requests(Database(settings))["unknown"] == 1
    assert (
        bot.post(event_path(event, "result"), json=report("confirmed", 2, "final")).json()["state"]
        == "confirmed"
    )
    pending = queue(customer, source, "keep_pending")
    with Database(settings).transaction() as connection:
        connection.execute("UPDATE action_requests SET created_at=now()-interval '40 days'")
        connection.execute(
            "UPDATE action_requests SET terminal_at=now()-interval '29 days' "
            "WHERE terminal_at IS NOT NULL"
        )
    assert maintain_requests(Database(settings)) == {"unknown": 1, "requests": 0}
    with Database(settings).transaction() as connection:
        connection.execute(
            "UPDATE action_requests SET terminal_at=now()-interval '31 days' "
            "WHERE terminal_at IS NOT NULL"
        )
    assert maintain_requests(Database(settings)) == {"unknown": 0, "requests": 1}
    with Database(settings).transaction() as connection:
        assert connection.execute("SELECT count(*) AS count FROM action_results").fetchone() == {
            "count": 0
        }
    assert (
        customer.get("/v1/action-requests/" + pending["action_request_id"]).json()["state"]
        == "unknown"
    )


def test_fixed_scan_does_not_lose_new_arrivals_and_long_poll_holds_no_lock(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    _, bot, customer, source, _ = shop
    with ThreadPoolExecutor(max_workers=1) as pool:
        waiting = pool.submit(lambda: bot.get("/v1/bot/events", params={"wait": 3}))
        time.sleep(0.2)
        queue(customer, source)
        assert len(waiting.result(timeout=5).json()["items"]) == 1
    queue(customer, source, "second_request")
    first = bot.get("/v1/bot/events", params={"limit": 1}).json()
    queue(customer, source, "new_arrival")
    bot.post(event_path(first["items"][0], "ack"), json={})
    assert (
        bot.get("/v1/bot/events", params={"cursor": first["next_cursor"], "wait": 1}).status_code
        == 400
    )
    tail = bot.get("/v1/bot/events", params={"cursor": first["next_cursor"]}).json()
    assert len(tail["items"]) == 1 and tail["next_cursor"] is None
    fresh = bot.get("/v1/bot/events").json()
    assert len(fresh["items"]) == 2
    assert bot.get("/v1/bot/requests", params={"cursor": first["next_cursor"]}).status_code == 400
    assert (
        bot.get("/v1/bot/events", params={"cursor": first["next_cursor"] + "bad"}).status_code
        == 400
    )


def test_concurrent_duplicates_and_ack_revocation_are_serialized(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, bot, customer, source, user_id = shop
    with ThreadPoolExecutor(max_workers=4) as pool:
        replies = list(pool.map(lambda _: queue(customer, source), range(4)))
    assert len({r["action_request_id"] for r in replies}) == 1
    event = bot.get("/v1/bot/events").json()["items"][0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        acknowledgement = pool.submit(lambda: bot.post(event_path(event, "ack"), json={}))
        revocation = pool.submit(lambda: owner.delete(path(source, "/grants/" + user_id)))
        ack, revoked = acknowledgement.result(), revocation.result()
    assert revoked.status_code == 204 and ack.status_code in {200, 409}
    with Database(settings).transaction() as connection:
        row = connection.execute("SELECT state,acknowledged_at FROM action_requests").fetchone()
    assert row is not None
    assert row["state"] == ("unknown" if ack.status_code == 200 else "cancelled")
    assert (row["acknowledged_at"] is not None) == (ack.status_code == 200)


def test_account_deactivation_and_channel_disable_keep_correct_uncertainty(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, bot, customer, source, _ = shop
    queue(customer, source)
    queue(customer, source, "acknowledged")
    events = bot.get("/v1/bot/events").json()["items"]
    bot.post(event_path(events[1], "ack"), json={})
    assert (
        customer.request(
            "DELETE", "/v1/account", json={"password": PASSWORD, "confirmation": "DELETE"}
        ).status_code
        == 204
    )
    assert bot.post(event_path(events[0], "ack"), json={}).status_code == 409
    assert bot.post(event_path(events[1], "result"), json=report()).json()["state"] == "confirmed"
    queue(owner, source, "owner_request")
    assert owner.delete(path(source)).status_code == 204
    assert bot.get("/v1/bot/events").json()["items"] == []
    with Database(settings).transaction() as connection:
        row = connection.execute(
            "SELECT state FROM action_requests WHERE idempotency_key='owner_request'"
        ).fetchone()
    assert row == {"state": "unknown"}


def test_action_and_result_outbox_failure_roll_back_every_write(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    _, bot, customer, source, _ = shop
    database = Database(settings)
    with database.transaction() as connection:
        connection.execute(
            "CREATE FUNCTION fail_action_hint() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN RAISE EXCEPTION 'synthetic fault'; END $$"
        )
        connection.execute(
            "CREATE TRIGGER action_fault BEFORE INSERT ON change_outbox "
            "FOR EACH ROW EXECUTE FUNCTION fail_action_hint()"
        )
    url = "/v1/channels/" + source["channel_id"] + "/actions"
    failed = customer.post(url, json=action_body(), headers={"Idempotency-Key": "safe_retry"})
    assert failed.status_code == 500
    with database.transaction() as connection:
        assert connection.execute("SELECT count(*) AS n FROM action_requests").fetchone() == {
            "n": 0
        }
        connection.execute("DROP TRIGGER action_fault ON change_outbox")
    request = queue(customer, source, "safe_retry")
    event = bot.get("/v1/bot/events").json()["items"][0]
    bot.post(event_path(event, "ack"), json={})
    with database.transaction() as connection:
        connection.execute(
            "CREATE TRIGGER action_fault BEFORE INSERT ON change_outbox "
            "FOR EACH ROW EXECUTE FUNCTION fail_action_hint()"
        )
    assert bot.post(event_path(event, "result"), json=report()).status_code == 500
    with database.transaction() as connection:
        assert connection.execute("SELECT count(*) AS n FROM action_results").fetchone() == {"n": 0}
        assert connection.execute("SELECT state FROM action_requests").fetchone() == {
            "state": "queued"
        }
        connection.execute("DROP TRIGGER action_fault ON change_outbox")
    assert bot.post(event_path(event, "result"), json=report()).json()["state"] == "confirmed"
    assert (
        customer.get("/v1/action-requests/" + request["action_request_id"]).json()["state"]
        == "confirmed"
    )


def test_public_to_selected_cancels_only_users_without_access(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, bot, customer, source, user_id = shop
    current = owner.get(path(source)).json()
    body = {
        "title": current["title"],
        "visibility": "public",
        "layout": {**current["layout"], "template_version": 3},
        "actions": current["actions"],
        "expected_template_version": 2,
    }
    owner.put(path(source), json=body)
    publish(owner, source, 3)
    owner.delete(path(source, "/grants/" + user_id))
    queue(customer, source)
    queue(owner, source, "owned_action")
    body.update(visibility="selected", expected_template_version=3)
    body["layout"]["template_version"] = 4
    owner.put(path(source), json=body)
    publish(owner, source, 4)
    with Database(settings).transaction() as connection:
        rows = connection.execute(
            "SELECT idempotency_key,state FROM action_requests ORDER BY sequence"
        ).fetchall()
    assert [r["state"] for r in rows] == ["cancelled", "queued"]
    assert len(bot.get("/v1/bot/events").json()["items"]) == 1


def test_result_order_expired_cursor_and_action_quota(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    _, bot, customer, source, _ = shop
    from marketob_api.cursors import Scan, encode_scan, session_binding

    queue(customer, source)
    event = bot.get("/v1/bot/events").json()["items"][0]
    bot.post(event_path(event, "ack"), json={})
    assert bot.post(event_path(event, "result"), json=report("processing", 2)).status_code == 200
    assert (
        bot.post(event_path(event, "result"), json=report("failed", 1, "old")).json()["code"]
        == "stale_result_revision"
    )
    with Database(settings).transaction() as connection:
        cursor = encode_scan(
            connection,
            session_binding(source["bot_id"], "events"),
            Scan(1, 0, int(time.time()) - 1),
        )
    assert bot.get("/v1/bot/events", params={"cursor": cursor}).status_code == 410
    limited = settings.model_copy(update={"action_rate_limit": 1})
    with client(limited) as restarted:
        restarted.cookies.update(customer.cookies)
        restarted.headers["X-CSRF-Token"] = customer.headers["X-CSRF-Token"]
        response = restarted.post(
            "/v1/channels/" + source["channel_id"] + "/actions",
            json=action_body(),
            headers={"Idempotency-Key": "second_request"},
        )
        assert response.status_code == 429 and int(response.headers["retry-after"]) >= 1


def test_bot_revoke_racing_request_never_deadlocks_or_loses_accepted_work(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, _, customer, source, _ = shop
    with ThreadPoolExecutor(max_workers=2) as pool:
        creation = pool.submit(
            lambda: customer.post(
                "/v1/channels/" + source["channel_id"] + "/actions",
                json=action_body(),
                headers={"Idempotency-Key": "race_request"},
            )
        )
        revocation = pool.submit(lambda: owner.delete("/v1/bots/" + source["bot_id"]))
        created, revoked = creation.result(), revocation.result()
    assert revoked.status_code == 204 and created.status_code in {202, 404}
    with Database(settings).transaction() as connection:
        rows = connection.execute("SELECT state FROM action_requests").fetchall()
    assert rows == ([{"state": "unknown"}] if created.status_code == 202 else [])


def test_account_deactivation_racing_result_preserves_real_result(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    _, bot, customer, source, _ = shop
    queue(customer, source)
    event = bot.get("/v1/bot/events").json()["items"][0]
    bot.post(event_path(event, "ack"), json={})
    with ThreadPoolExecutor(max_workers=2) as pool:
        reporting = pool.submit(lambda: bot.post(event_path(event, "result"), json=report()))
        deactivation = pool.submit(
            lambda: customer.request(
                "DELETE", "/v1/account", json={"password": PASSWORD, "confirmation": "DELETE"}
            )
        )
        result, deleted = reporting.result(), deactivation.result()
    assert result.status_code == 200 and deleted.status_code == 204
    with Database(settings).transaction() as connection:
        assert connection.execute("SELECT state FROM action_requests").fetchone() == {
            "state": "confirmed"
        }


def test_grant_racing_deactivation_with_pending_work_does_not_deadlock(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, _, customer, source, user_id = shop
    queue(customer, source)
    with ThreadPoolExecutor(max_workers=2) as pool:
        granting = pool.submit(lambda: owner.put(path(source, "/grants/" + user_id), json={}))
        deactivation = pool.submit(
            lambda: customer.request(
                "DELETE", "/v1/account", json={"password": PASSWORD, "confirmation": "DELETE"}
            )
        )
        grant, deleted = granting.result(), deactivation.result()
    assert deleted.status_code == 204 and grant.status_code in {204, 404}
    with Database(settings).transaction() as connection:
        assert connection.execute("SELECT count(*) AS n FROM grants").fetchone() == {"n": 0}
        assert connection.execute("SELECT state FROM action_requests").fetchone() == {
            "state": "cancelled"
        }
