"""Independent layouts, current source permissions and optimistic autosave on PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any

import pytest
from fastapi.testclient import TestClient
from marketob_api.config import Settings

from tests.test_actions import catalog
from tests.test_channels import path, publish, validate
from tests.test_favorites import ready
from tests.test_identity import PASSWORD, client, register
from tests.test_identity import settings as settings
from tests.test_ingestion import draft, message
from tests.test_ingestion import gateway as gateway

pytestmark = pytest.mark.integration


def body(*channels: dict[str, Any]) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    for channel in channels:
        for block in channel["layout"]["blocks"]:
            blocks.append({**deepcopy(block), "block_id": "personal_" + str(len(blocks))})
    return {
        "title": "My daily space",
        "expected_template_version": 0,
        "layout": {
            "schema_version": "1.0",
            "template_version": 1,
            "theme": "blue",
            "density": "compact",
            "blocks": blocks,
        },
    }


def create(http: TestClient, value: dict[str, Any], key: str = "create_first") -> dict[str, Any]:
    result = http.post("/v1/personal-pages", json=value, headers={"Idempotency-Key": key})
    assert result.status_code == 201, result.text
    validate("PersonalPage", result.json())
    return dict(result.json())


def replacement(page: dict[str, Any]) -> dict[str, Any]:
    version = page["layout"]["template_version"]
    return {
        "title": page["title"],
        "expected_template_version": version,
        "layout": {**deepcopy(page["layout"]), "template_version": version + 1},
    }


def test_two_channel_layout_edit_and_undo_never_change_publisher(
    gateway: tuple[TestClient, TestClient, dict[str, Any]],
) -> None:
    owner, bot, source = gateway
    catalog(owner, bot, source, "public")
    news = draft(owner, source["bot_id"], "daily-news")
    ready(owner, bot, news)
    product = owner.get(path(source)).json()
    news_page = owner.get(path(news)).json()
    page = create(owner, body(product, news_page))
    url = "/v1/personal-pages/" + page["page_id"]
    snap = owner.get(url + "/snapshot").json()
    validate("PageSnapshot", snap)
    assert [b["available"] for b in snap["blocks"]] == [True, True]
    assert snap["blocks"][0]["actions"][0]["action_id"] == "purchase"
    changed = replacement(page)
    changed["layout"]["blocks"].reverse()
    changed["layout"]["blocks"][1]["view"] = "list"
    changed["layout"]["theme"] = "ink"
    saved = owner.put(url, json=changed)
    assert saved.status_code == 200
    undo = {**body(product, news_page), "expected_template_version": 2}
    undo["layout"]["template_version"] = 3
    assert owner.put(url, json=undo).status_code == 200
    assert owner.get(path(source)).json() == product and owner.get(path(news)).json() == news_page
    assert bot.post("/v1/bot/messages", json=message(news, 2, "news_updated")).status_code == 200
    assert owner.get(url + "/snapshot").json()["blocks"][1]["record"]["source_revision"] == 2


def test_autosave_concurrency_and_identical_replay(settings: Settings) -> None:
    with client(settings) as first, client(settings) as second:
        register(first, "reader")
        login = second.post("/v1/auth/login", json={"username": "reader", "password": PASSWORD})
        second.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        page = create(first, body())
        url = "/v1/personal-pages/" + page["page_id"]
        one = replacement(page)
        two = replacement(page)
        one["title"] = "First"
        two["title"] = "Second"
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(c.put, url, json=b) for c, b in ((first, one), (second, two))]
            results = [f.result() for f in futures]
        assert sorted(r.status_code for r in results) == [200, 409]
        winning = one if results[0].status_code == 200 else two
        assert first.put(url, json=winning).status_code == 200
        assert second.get(url).json()["layout"]["template_version"] == 2
        later = replacement(second.get(url).json())
        later["title"] = "Later"
        assert second.put(url, json=later).status_code == 200
        assert first.put(url, json=winning).status_code == 409


def test_creation_retry_and_owned_page_isolation(settings: Settings) -> None:
    with client(settings) as owner, client(settings) as other:
        register(owner, "owner")
        register(other, "other")
        page = create(owner, body())
        url = "/v1/personal-pages/" + page["page_id"]
        assert create(owner, body()) == page
        assert len(owner.get("/v1/personal-pages").json()["items"]) == 1
        assert other.get(url).status_code == 404 and other.get(url + "/snapshot").status_code == 404
        assert other.put(url, json=replacement(page)).status_code == 404
        assert other.delete(url).status_code == 204 and owner.get(url).status_code == 200
        altered = body()
        altered["title"] = "Different"
        assert (
            owner.post(
                "/v1/personal-pages", json=altered, headers={"Idempotency-Key": "create_first"}
            ).status_code
            == 409
        )
        create(owner, body(), "create_second")
        cursor = owner.get("/v1/personal-pages?limit=1").json()["next_cursor"]
        assert other.get("/v1/personal-pages", params={"cursor": cursor}).status_code == 400
        assert owner.delete(url).status_code == 204
        assert owner.get(url).status_code == 404
        assert (
            owner.post(
                "/v1/personal-pages", json=body(), headers={"Idempotency-Key": "create_first"}
            ).status_code
            == 409
        )


def test_revoked_reference_can_be_reordered_but_not_added(
    settings: Settings, gateway: tuple[TestClient, TestClient, dict[str, Any]]
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source, "selected")
    published = owner.get(path(source)).json()
    with client(settings) as reader:
        user = register(reader, "reader")
        grant = path(source, "/grants/" + user)
        assert (
            reader.post(
                "/v1/personal-pages",
                json=body(published),
                headers={"Idempotency-Key": "denied_create"},
            ).status_code
            == 404
        )
        assert owner.put(grant, json={}).status_code == 204
        page = create(reader, body(published))
        url = "/v1/personal-pages/" + page["page_id"]
        assert owner.delete(grant).status_code == 204
        snap = reader.get(url + "/snapshot").json()
        validate("PageSnapshot", snap)
        assert snap["blocks"] == [{"block_id": "personal_0", "available": False}]
        changed = replacement(page)
        changed["layout"]["blocks"][0]["view"] = "article"
        assert reader.put(url, json=changed).status_code == 200
        assert (
            reader.post(
                "/v1/personal-pages",
                json=body(published),
                headers={"Idempotency-Key": "new_denied"},
            ).status_code
            == 404
        )
        assert owner.put(grant, json={}).status_code == 204
        assert reader.get(url + "/snapshot").json()["blocks"][0]["available"]
        assert owner.delete(path(source)).status_code == 204
        assert reader.get(url + "/snapshot").json()["blocks"] == [
            {"block_id": "personal_0", "available": False}
        ]
        removed = replacement(reader.get(url).json())
        removed["layout"]["blocks"] = []
        assert reader.put(url, json=removed).status_code == 200


def test_tombstone_unpublished_binding_and_removed_action_are_rechecked(
    gateway: tuple[TestClient, TestClient, dict[str, Any]],
) -> None:
    owner, bot, source = gateway
    catalog(owner, bot, source, "public")
    channel = owner.get(path(source)).json()
    page = create(owner, body(channel))
    url = "/v1/personal-pages/" + page["page_id"] + "/snapshot"
    changed = {
        "title": channel["title"],
        "visibility": "public",
        "actions": [],
        "expected_template_version": 2,
        "layout": {**deepcopy(channel["layout"]), "template_version": 3},
    }
    changed["layout"]["blocks"][0]["action_ids"] = []
    assert owner.put(path(source), json=changed).status_code == 200
    publish(owner, source, 3)
    assert owner.get(url).json()["blocks"][0]["actions"] == []
    changed["expected_template_version"] = 3
    changed["layout"]["template_version"] = 4
    changed["layout"]["blocks"] = []
    assert owner.put(path(source), json=changed).status_code == 200
    publish(owner, source, 4)
    assert owner.get(url).json()["blocks"] == [{"block_id": "personal_0", "available": False}]
    channel = owner.post(
        path(source, "/rollback"),
        json={"expected_template_version": 4, "target_template_version": 2},
    ).json()
    assert owner.get(url).json()["blocks"][0]["available"]
    tombstone = message(source, 2, "delete_item")
    tombstone.pop("payload")
    tombstone["kind"] = "delete"
    assert bot.post("/v1/bot/messages", json=tombstone).status_code == 200
    assert owner.get(url).json()["blocks"] == [{"block_id": "personal_0", "available": False}]


def test_invalid_visualizations_hidden_resources_and_payloads_are_rejected(
    gateway: tuple[TestClient, TestClient, dict[str, Any]],
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source)
    channel = owner.get(path(source)).json()
    original = body(channel)
    for mutation in ("view", "duplicate", "script", "hidden"):
        value = deepcopy(original)
        if mutation == "view":
            value["layout"]["blocks"][0]["view"] = "line"
        if mutation == "duplicate":
            value["layout"]["blocks"] *= 2
        if mutation == "script":
            value["layout"]["html"] = "<script>alert(1)</script>"
        if mutation == "hidden":
            value["layout"]["blocks"][0]["source"]["resource_id"] = "hidden"
        result = owner.post(
            "/v1/personal-pages", json=value, headers={"Idempotency-Key": "invalid_" + mutation}
        )
        assert result.status_code == (404 if mutation == "hidden" else 422)


def test_page_capacity_and_maximum_block_count(settings: Settings) -> None:
    with client(settings) as owner:
        register(owner, "owner")
        oversized = body()
        oversized["layout"]["blocks"] = [
            {
                "block_id": "block_" + str(i),
                "source": {"channel_id": "ch_unknown", "resource_id": "item"},
                "content_type": "news",
                "view": "article",
                "action_ids": [],
            }
            for i in range(51)
        ]
        assert (
            owner.post(
                "/v1/personal-pages",
                json=oversized,
                headers={"Idempotency-Key": "oversized_create"},
            ).status_code
            == 422
        )
        for i in range(20):
            create(owner, body(), "create_page_" + str(i))
        denied = owner.post(
            "/v1/personal-pages", json=body(), headers={"Idempotency-Key": "create_too_many"}
        )
        assert denied.status_code == 409 and denied.json()["code"] == "page_limit"
        page = owner.get("/v1/personal-pages").json()["items"][0]
        assert owner.delete("/v1/personal-pages/" + page["page_id"]).status_code == 204
        create(owner, body(), "create_after_delete")
