"""Published layout isolation, live records, authorization and immutable rollback on PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.payloads import SCHEMAS

from tests.test_identity import business, client, register
from tests.test_identity import settings as settings
from tests.test_ingestion import draft, message
from tests.test_ingestion import gateway as gateway

pytestmark = pytest.mark.integration


def path(source: dict[str, Any], suffix: str = "") -> str:
    return "/v1/owner/channels/" + str(source["channel_id"]) + suffix


def edit(source: dict[str, Any], *, visibility: str = "selected") -> dict[str, Any]:
    version = source["layout"]["template_version"]
    return {
        "title": source["title"],
        "visibility": visibility,
        "expected_template_version": version,
        "layout": {
            **source["layout"],
            "template_version": version + 1,
            "blocks": [
                {
                    "block_id": "news",
                    "source": {"channel_id": source["channel_id"], "resource_id": "item_one"},
                    "content_type": "news",
                    "view": "compact",
                    "action_ids": [],
                }
            ],
        },
        "actions": [],
    }


def publish(owner: TestClient, source: dict[str, Any], version: int = 2) -> dict[str, Any]:
    result = owner.post(path(source, "/publish"), json={"expected_template_version": version})
    assert result.status_code == 200, result.text
    return dict(result.json())


def validate(name: str, value: dict[str, Any]) -> None:
    Draft202012Validator({"$defs": SCHEMAS, "$ref": "#/$defs/" + name}).validate(value)


def test_draft_isolation_live_data_and_immutable_rollback(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    url = "/v1/channels/" + source["slug"]
    assert bot.post("/v1/bot/messages", json=message(source)).status_code == 200
    with client(settings) as anonymous:
        assert anonymous.get(url).status_code == 404
        first = owner.put(path(source), json=edit(source, visibility="public")).json()
        assert (
            owner.get(path(source, "/preview")).json()["records"][0]["content"]["title"]
            == "Synthetic news"
        )
        publish(owner, source)
        initial = anonymous.get(url)
        assert initial.status_code == 200
        validate("Snapshot", initial.json())
        assert "org_id" not in initial.text and "owner_user_id" not in initial.text
        changed = edit(first, visibility="selected")
        changed["title"] = "Unpublished title"
        changed["layout"]["theme"] = "ink"
        assert owner.put(path(source), json=changed).status_code == 200
        assert anonymous.get(url).json() == initial.json()
        update = message(source, 2, "second")
        update["payload"]["title"] = "New live data"
        assert bot.post("/v1/bot/messages", json=update).status_code == 200
        assert anonymous.get(url).json()["records"][0]["source_revision"] == 2
        publish(owner, source, 3)
        assert anonymous.get(url).status_code == 404
        rolled = owner.post(
            path(source, "/rollback"),
            json={"expected_template_version": 3, "target_template_version": 2},
        )
        assert rolled.status_code == 200 and rolled.json()["layout"]["template_version"] == 4
        live = anonymous.get(url).json()
        assert live["channel"]["title"] == source["title"]
        assert live["records"][0]["content"]["title"] == "New live data"
        versions = owner.get(path(source, "/versions")).json()
        validate("PageVersionList", versions)
        assert [v["channel"]["layout"]["template_version"] for v in versions["items"]] == [
            1,
            2,
            3,
            4,
        ]
        assert versions["items"][1]["channel"]["layout"]["theme"] == "blue"
        assert [v["channel"]["published"] for v in versions["items"]] == [False, False, False, True]


def test_etag_checks_session_grants_and_visibility_before_304(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    bot.post("/v1/bot/messages", json=message(source))
    owner.put(path(source), json=edit(source))
    publish(owner, source)
    url = "/v1/channels/" + source["slug"]
    with client(settings) as reader, client(settings) as outsider:
        reader_id = register(reader, "reader")
        register(outsider, "outsider")
        owner.put(path(source, "/grants/" + reader_id), json={})
        initial = reader.get(url)
        etag = initial.headers["etag"]
        assert initial.headers["cache-control"] == "no-store"
        assert "Cookie" in initial.headers["vary"]
        assert reader.get(url, headers={"If-None-Match": '"wrong", W/' + etag}).status_code == 304
        assert outsider.get(url, headers={"If-None-Match": etag}).status_code == 404
        assert owner.get(url, headers={"If-None-Match": etag}).status_code == 200
        owner.delete(path(source, "/grants/" + reader_id))
        revoked = reader.get(url, headers={"If-None-Match": "*"})
        assert revoked.status_code == 404 and "etag" not in revoked.headers
        assert "Synthetic" not in revoked.text
        owner.put(path(source, "/grants/" + reader_id), json={})
        reader.delete("/v1/auth/session")
        assert reader.get(url, headers={"If-None-Match": etag}).status_code == 404


def test_default_selected_empty_publish_delete_and_bot_revocation(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    created = owner.post(
        "/v1/channels", json={"bot_id": source["bot_id"], "slug": "empty", "title": "Empty"}
    )
    assert created.status_code == 201 and created.json()["visibility"] == "selected"
    empty = created.json()
    publish(owner, empty, 1)
    response = owner.get("/v1/channels/empty")
    validate("Snapshot", response.json())
    assert response.json()["records"] == [] and response.json()["data_revision"] == 0
    assert owner.delete(path(empty)).status_code == 204
    assert owner.delete(path(empty)).status_code == 204
    assert owner.get("/v1/channels/empty").status_code == 404
    assert owner.get(path(empty)).status_code == 404
    bot.post("/v1/bot/messages", json=message(source))
    owner.put(path(source), json=edit(source))
    publish(owner, source)
    assert owner.delete("/v1/bots/" + source["bot_id"]).status_code == 204
    assert owner.get("/v1/channels/" + source["slug"]).status_code == 404
    assert (
        owner.post(path(source, "/publish"), json={"expected_template_version": 2}).status_code
        == 404
    )


def test_missing_sources_validation_and_current_type_filter(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    body = edit(source)
    assert owner.put(path(source), json=body).status_code == 200
    assert (
        owner.post(path(source, "/publish"), json={"expected_template_version": 2}).status_code
        == 409
    )
    bot.post("/v1/bot/messages", json=message(source))
    publish(owner, source)
    deletion = message(source, 2, "deleted")
    deletion.pop("payload")
    deletion["kind"] = "delete"
    assert bot.post("/v1/bot/messages", json=deletion).status_code == 200
    snap = owner.get("/v1/channels/" + source["slug"]).json()
    assert snap["records"] == [] and len(snap["channel"]["layout"]["blocks"]) == 1
    result = owner.post(
        path(source, "/rollback"),
        json={"expected_template_version": 2, "target_template_version": 2},
    )
    assert result.status_code == 409
    assert owner.get(path(source)).json()["layout"]["template_version"] == 2
    assert len(owner.get(path(source, "/versions")).json()["items"]) == 2
    product = message(source, 3, "product")
    product.update(
        kind="data",
        content_type="product",
        payload={
            "title": "Soap",
            "description": "Demo",
            "price": {"amount_minor": 200, "currency": "EUR"},
            "availability": "in_stock",
        },
    )
    assert bot.post("/v1/bot/messages", json=product).status_code == 200
    assert owner.get("/v1/channels/" + source["slug"]).json()["records"] == []
    assert owner.get(path(source, "/resources")).json()["items"][0]["content_type"] == "product"


def test_foreign_bindings_duplicate_ids_and_pilot_actions(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, _, source = gateway
    with client(settings) as bob:
        register(bob, "bob")
        business(bob)
        for suffix in ("", "/preview", "/resources", "/versions"):
            assert bob.get(path(source, suffix)).status_code == 404
        assert bob.put(path(source), json=edit(source)).status_code == 404
    bad = edit(source)
    bad["layout"]["blocks"][0]["source"]["channel_id"] = "ch_foreign"
    assert owner.put(path(source), json=bad).status_code == 422
    bad = edit(source)
    bad["layout"]["blocks"] *= 2
    assert owner.put(path(source), json=bad).json()["code"] == "duplicate_identifier"
    body = edit(source)
    block = body["layout"]["blocks"][0]
    block.update(content_type="product", view="card", action_ids=["purchase"])
    body["actions"] = [
        {
            "action_id": "purchase",
            "resource_id": "item_one",
            "kind": "request_purchase",
            "label": "Request purchase",
        }
    ]
    for change in ({"kind": "add_to_cart"}, {"resource_id": "wrong"}, {"label": "Buy"}):
        bad = deepcopy(body)
        bad["actions"][0].update(change)
        assert owner.put(path(source), json=bad).status_code == 422
    assert owner.put(path(source), json=body).status_code == 200
    stale = owner.put(path(source), json=body)
    assert stale.status_code == 409


def test_fixed_scans_limits_and_session_bound_cursors(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    second = draft(owner, source["bot_id"], "second")
    first = owner.get("/v1/owner/channels", params={"limit": 1}).json()
    validate("ChannelList", first)
    third = draft(owner, source["bot_id"], "third")
    rest = owner.get("/v1/owner/channels", params={"cursor": first["next_cursor"]}).json()
    assert [c["channel_id"] for c in rest["items"]] == [second["channel_id"]]
    assert third["channel_id"] not in str(rest)
    assert (
        owner.get(path(source, "/resources"), params={"cursor": first["next_cursor"]}).status_code
        == 400
    )
    for index in range(3):
        body = message(source, mid="m" + str(index))
        body["resource_id"] = "r" + str(index)
        assert bot.post("/v1/bot/messages", json=body).status_code == 200
    page = owner.get(path(source, "/resources"), params={"limit": 1}).json()
    validate("OwnedResourceList", page)
    assert len(page["items"]) == 1 and page["next_cursor"]
    tail = owner.get(path(source, "/resources"), params={"cursor": page["next_cursor"]}).json()
    assert len(tail["items"]) == 2 and tail["next_cursor"] is None
    assert owner.get(path(source, "/versions"), params={"limit": 101}).status_code == 422
    assert (
        owner.get(
            path(source, "/resources"), params={"cursor": page["next_cursor"] + "x"}
        ).status_code
        == 400
    )


def test_concurrent_edit_has_one_winner_and_publish_failure_is_atomic(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    bot.post("/v1/bot/messages", json=message(source))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: owner.put(path(source), json=edit(source)), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    with Database(settings).transaction() as connection:
        connection.execute(
            "CREATE FUNCTION reject_publish() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN RAISE EXCEPTION 'synthetic'; END $$"
        )
        connection.execute(
            "CREATE TRIGGER publication_fault BEFORE INSERT ON change_outbox "
            "FOR EACH ROW EXECUTE FUNCTION reject_publish()"
        )
    failed = owner.post(path(source, "/publish"), json={"expected_template_version": 2})
    assert failed.status_code == 500
    assert owner.get("/v1/channels/" + source["slug"]).status_code == 404
    assert all(
        v["published_at"] is None for v in owner.get(path(source, "/versions")).json()["items"]
    )
    with Database(settings).transaction() as connection:
        connection.execute("DROP TRIGGER publication_fault ON change_outbox")
    publish(owner, source)


def test_snapshot_projects_only_published_typed_sources(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    payloads = {
        "news": {"title": "News", "body": "Plain text"},
        "product": {
            "title": "Soap",
            "description": "Demo",
            "availability": "in_stock",
            "price": {"amount_minor": 200, "currency": "EUR"},
        },
        "chart": {
            "title": "Daily count",
            "x_label": "Day",
            "x_kind": "number",
            "y_label": "Items",
            "unit": "items",
            "series": [{"name": "Count", "points": [{"x": 1, "y": 4}]}],
        },
    }
    body = edit(source)
    body["layout"]["blocks"] = []
    for kind, view in (("news", "article"), ("product", "card"), ("chart", "line")):
        payload = message(source, mid=kind)
        payload.update(kind="data", content_type=kind, resource_id=kind, payload=payloads[kind])
        assert bot.post("/v1/bot/messages", json=payload).status_code == 200
        body["layout"]["blocks"].append(
            {
                "block_id": kind,
                "source": {"channel_id": source["channel_id"], "resource_id": kind},
                "content_type": kind,
                "view": view,
                "action_ids": ["purchase"] if kind == "product" else [],
            }
        )
    body["actions"] = [
        {
            "action_id": "purchase",
            "resource_id": "product",
            "kind": "request_purchase",
            "label": "Request purchase",
        }
    ]
    hidden = message(source, mid="hidden")
    hidden["payload"]["title"] = "Never exposed"
    bot.post("/v1/bot/messages", json=hidden)
    assert owner.put(path(source), json=body).status_code == 200
    publish(owner, source)
    result = owner.get("/v1/channels/" + source["slug"])
    validate("Snapshot", result.json())
    assert len(result.json()["records"]) == 3 and "Never exposed" not in result.text
    etag = result.headers["etag"]
    update = message(source, 2, "news_update")
    update["resource_id"] = "news"
    bot.post("/v1/bot/messages", json=update)
    assert (
        owner.get("/v1/channels/" + source["slug"], headers={"If-None-Match": etag}).status_code
        == 200
    )
