"""Server templates preserve layout but never transfer source permissions."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from marketob_api.config import Settings
from marketob_api.database import Database
from psycopg.types.json import Jsonb

from tests.test_channels import path, validate
from tests.test_favorites import ready
from tests.test_identity import PASSWORD, client, register
from tests.test_identity import settings as settings
from tests.test_ingestion import draft
from tests.test_ingestion import gateway as gateway
from tests.test_personal_pages import body, create, replacement

pytestmark = pytest.mark.integration


def share(http: TestClient, page: dict[str, Any], key: str = "create_share") -> dict[str, Any]:
    result = http.post(
        "/v1/personal-pages/" + page["page_id"] + "/shares",
        json={"expected_template_version": page["layout"]["template_version"]},
        headers={"Idempotency-Key": key},
    )
    assert result.status_code == 201, result.text
    validate("Share", result.json())
    return dict(result.json())


def imported(http: TestClient, code: str, key: str = "import_first") -> dict[str, Any]:
    result = http.post(
        "/v1/template-imports", json={"code": code}, headers={"Idempotency-Key": key}
    )
    assert result.status_code == 201, result.text
    validate("PersonalPage", result.json())
    return dict(result.json())


def test_two_recipients_independent_copies_and_source_permissions(
    settings: Settings,
    gateway: tuple[TestClient, TestClient, dict[str, Any]],
) -> None:
    owner, bot, source = gateway
    ready(owner, bot, source, "selected")
    public = draft(owner, source["bot_id"], "public-news")
    ready(owner, bot, public)
    page = create(owner, body(owner.get(path(source)).json(), owner.get(path(public)).json()))
    link = share(owner, page)
    assert (
        29
        < (datetime.fromisoformat(link["expires_at"]) - datetime.now(UTC)).total_seconds() / 86400
        <= 30
    )
    with client(settings) as alice, client(settings) as bob:
        user = register(alice, "import_alice")
        register(bob, "import_bob")
        assert owner.put(path(source, "/grants/" + user), json={}).status_code == 204
        for recipient, unavailable in [(alice, []), (bob, ["personal_0"])]:
            result = recipient.post("/v1/template-imports/preview", json={"code": link["code"]})
            assert result.status_code == 200
            validate("ImportPreview", result.json())
            assert result.json()["unavailable_blocks"] == unavailable
            assert "Synthetic news" not in result.text and "Local pilot" not in result.text
        a, b = imported(alice, link["code"]), imported(bob, link["code"])
        assert a["title"].endswith(" (copy)") and a["layout"] == page["layout"] == b["layout"]
        snap = bob.get("/v1/personal-pages/" + b["page_id"] + "/snapshot").json()
        assert snap["blocks"][0] == {"block_id": "personal_0", "available": False}
        assert snap["blocks"][1]["available"]
        change = replacement(page)
        change["layout"]["theme"] = "ink"
        assert owner.put("/v1/personal-pages/" + page["page_id"], json=change).status_code == 200
        assert imported(alice, link["code"], "another_import")["layout"]["theme"] == "blue"
        assert owner.delete(path(source, "/grants/" + user)).status_code == 204
        assert not alice.get("/v1/personal-pages/" + a["page_id"] + "/snapshot").json()["blocks"][
            0
        ]["available"]
        assert owner.delete(path(public)).status_code == 204
        assert all(
            not x["available"]
            for x in bob.get("/v1/personal-pages/" + b["page_id"] + "/snapshot").json()["blocks"]
        )


def test_revoke_delete_expiry_and_existing_replay(settings: Settings) -> None:
    with client(settings) as owner, client(settings) as reader:
        register(owner, "owner")
        register(reader, "reader")
        page = create(owner, body())
        link = share(owner, page)
        copy = imported(reader, link["code"])
        assert reader.delete("/v1/shares/" + link["share_id"]).status_code == 204
        assert owner.get("/v1/personal-pages/" + page["page_id"] + "/shares").json()["items"]
        assert owner.delete("/v1/shares/" + link["share_id"]).status_code == 204
        assert imported(reader, link["code"])["page_id"] == copy["page_id"]
        assert (
            reader.post(
                "/v1/template-imports",
                json={"code": link["code"]},
                headers={"Idempotency-Key": "new_after_revoke"},
            ).status_code
            == 404
        )
        expiry = share(owner, page, "expires_link")
        with Database(settings).transaction() as db:
            db.execute(
                "UPDATE shared_templates SET expires_at=now()-interval '1 second' "
                "WHERE share_id=%s",
                (expiry["share_id"],),
            )
        assert (
            reader.post("/v1/template-imports/preview", json={"code": expiry["code"]}).status_code
            == 404
        )
        deleted = share(owner, page, "delete_link")
        assert owner.delete("/v1/personal-pages/" + page["page_id"]).status_code == 204
        assert (
            reader.post("/v1/template-imports/preview", json={"code": deleted["code"]}).status_code
            == 404
        )
        assert reader.get("/v1/personal-pages/" + copy["page_id"]).status_code == 200


def test_create_import_replay_concurrency_and_owner_isolation(settings: Settings) -> None:
    with client(settings) as owner, client(settings) as reader, client(settings) as other:
        register(owner, "owner")
        register(reader, "reader")
        result = other.post("/v1/auth/login", json={"username": "reader", "password": PASSWORD})
        other.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        page = create(owner, body())
        link = share(owner, page)
        assert share(owner, page) == link
        assert reader.get("/v1/personal-pages/" + page["page_id"] + "/shares").status_code == 404
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda c: imported(c, link["code"]), [reader, other]))
        assert results[0] == results[1]
        second = share(owner, page, "second_share")
        assert (
            reader.post(
                "/v1/template-imports",
                json={"code": second["code"]},
                headers={"Idempotency-Key": "import_first"},
            ).status_code
            == 409
        )
        assert reader.delete("/v1/personal-pages/" + results[0]["page_id"]).status_code == 204
        assert (
            reader.post(
                "/v1/template-imports",
                json={"code": link["code"]},
                headers={"Idempotency-Key": "import_first"},
            ).status_code
            == 409
        )


def test_invalid_oversized_unknown_version_and_inactive_author(settings: Settings) -> None:
    with client(settings) as owner, client(settings) as reader:
        register(owner, "owner")
        register(reader, "reader")
        page = create(owner, body())
        link = share(owner, page)
        for value in [
            {"code": "broken"},
            {"code": "x" * 1000},
            {"code": link["code"], "layout": page["layout"]},
        ]:
            assert reader.post("/v1/template-imports/preview", json=value).status_code == 422
        assert (
            reader.post("/v1/template-imports/preview", json={"code": "x" * 32}).status_code == 404
        )
        assert reader.post("/v1/template-imports", json={"code": link["code"]}).status_code == 422
        corrupt = deepcopy(page["layout"])
        corrupt["schema_version"] = "999.0"
        with Database(settings).transaction() as db:
            db.execute(
                "UPDATE shared_templates SET layout=%s WHERE share_id=%s",
                (Jsonb(corrupt), link["share_id"]),
            )
        assert (
            reader.post("/v1/template-imports/preview", json={"code": link["code"]}).status_code
            == 422
        )
        valid = share(owner, page, "valid_again")
        assert (
            owner.request("DELETE", "/v1/account", json={"password": PASSWORD}).status_code == 204
        )
        assert (
            reader.post("/v1/template-imports/preview", json={"code": valid["code"]}).status_code
            == 404
        )


def test_share_limits_and_version_guard(settings: Settings) -> None:
    with client(settings.model_copy(update={"write_rate_limit": 1000})) as owner:
        register(owner, "owner")
        page = create(owner, body())
        url = "/v1/personal-pages/" + page["page_id"] + "/shares"
        for value, code in [
            ({"expected_template_version": 2}, 409),
            ({"expected_template_version": 1, "expires_at": "2000-01-01T00:00:00Z"}, 422),
        ]:
            assert (
                owner.post(
                    url, json=value, headers={"Idempotency-Key": "invalid_share"}
                ).status_code
                == code
            )
        links = [share(owner, page, "share_limit_" + str(i)) for i in range(20)]
        assert len(owner.get(url).json()["items"]) == 20
        assert (
            owner.post(
                url,
                json={"expected_template_version": 1},
                headers={"Idempotency-Key": "over_share_limit"},
            ).status_code
            == 409
        )
        assert owner.delete("/v1/shares/" + links[0]["share_id"]).status_code == 204
        share(owner, page, "after_revoke")
