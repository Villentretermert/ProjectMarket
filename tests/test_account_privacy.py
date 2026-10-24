"""D46: personal export, atomic ownership handoff, and guarded account erasure."""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from marketob_api.config import Settings
from marketob_api.database import Database

from tests.test_access_invalidation import fill_queue
from tests.test_actions import event_path, queue
from tests.test_actions import shop as shop
from tests.test_channels import path, validate
from tests.test_identity import PASSWORD, business, client, register
from tests.test_identity import settings as settings
from tests.test_ingestion import gateway as gateway
from tests.test_personal_pages import body, create
from tests.test_privacy import choose
from tests.test_sharing import share
from tests.test_teams import add

pytestmark = pytest.mark.integration
DELETE = {"password": PASSWORD, "confirmation": "DELETE"}


def test_export_projection_and_private_source_revocation(shop: tuple[Any, ...]) -> None:
    owner, bot, reader, source, uid = shop
    personal = create(reader, body(owner.get(path(source)).json()))
    foreign = create(owner, {**body(), "title": "Foreign personal title"})
    request = queue(reader, source)
    other_request = queue(owner, source, "owner-request")
    assert reader.put("/v1/favorites/" + source["channel_id"], json={}).status_code == 204
    choose(reader, source["channel_id"])
    assert owner.delete(path(source, "/grants/" + uid)).status_code == 204
    exported = {}
    for section in ("profile", "favorites", "spaces", "requests", "events"):
        response = reader.get("/v1/account/export", params={"section": section})
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        validate("PersonalExportPage", response.json())
        exported[section] = response.json()["items"]
    assert exported["profile"][0]["user_id"] == uid
    assert exported["spaces"][0]["page_id"] == personal["page_id"]
    assert exported["requests"][0]["action_request_id"] == request["action_request_id"]
    assert exported["requests"][0]["state"] == "cancelled"
    assert exported["favorites"][0]["channel_id"] == source["channel_id"]
    assert exported["events"][0]["events"] == ["news.published"]
    serialized = json.dumps(exported)
    for forbidden in (
        PASSWORD,
        "password_hash",
        "csrf_token",
        "api_key",
        "actor_ref",
        "idempotency_key",
        "body_hash",
        "summary",
        "Soap",
        foreign["page_id"],
        other_request["action_request_id"],
    ):
        assert forbidden not in serialized
    assert reader.get("/v1/account/export?section=keys").status_code == 422
    assert reader.get("/v1/account/export?user_id=someone").json()["items"][0]["user_id"] == uid


def test_export_pagination_is_bound_to_session_section_and_upper_bound(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, _, reader, source, _ = shop
    first = queue(reader, source, "export-first")
    second = queue(reader, source, "export-second")
    page = reader.get("/v1/account/export?section=requests&limit=1").json()
    assert [r["action_request_id"] for r in page["items"]] == [first["action_request_id"]]
    cursor = page["next_cursor"]
    queue(reader, source, "export-after-upper")
    params = {"section": "requests", "cursor": cursor, "limit": 1}
    following = reader.get("/v1/account/export", params=params).json()
    assert following["next_cursor"] is None
    assert following["items"][0]["action_request_id"] == second["action_request_id"]
    assert owner.get("/v1/account/export", params=params).status_code == 400
    assert (
        reader.get("/v1/account/export", params={**params, "section": "events"}).status_code == 400
    )
    assert (
        reader.get("/v1/account/export", params={**params, "cursor": cursor + "x"}).status_code
        == 400
    )
    with client(settings) as anonymous:
        assert anonymous.get("/v1/account/export").status_code == 401


def test_delete_requires_both_confirmations_and_removes_only_personal_setup(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, bot, reader, source, uid = shop
    own = create(reader, body())
    link = share(reader, own)
    retained = create(owner, body())
    choose(reader, source["channel_id"])
    choose(owner, source["channel_id"])
    assert reader.put("/v1/favorites/" + source["channel_id"], json={}).status_code == 204
    pending = queue(reader, source)
    acknowledged = queue(reader, source, "already-sent")
    event = next(
        e
        for e in bot.get("/v1/bot/events").json()["items"]
        if e["action_request_id"] == acknowledged["action_request_id"]
    )
    assert bot.post(event_path(event, "ack"), json={}).status_code == 200
    for payload, status in (
        ({"password": PASSWORD}, 422),
        ({**DELETE, "confirmation": "delete"}, 422),
        ({**DELETE, "password": "wrong-password"}, 403),
    ):
        assert reader.request("DELETE", "/v1/account", json=payload).status_code == status
        assert reader.get("/v1/auth/session").status_code == 200
    assert (
        reader.request(
            "DELETE", "/v1/account", json=DELETE, headers={"X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    preview = reader.get("/v1/account/deletion-preview").json()
    validate("DeletionPreview", preview)
    assert preview == {
        "can_delete": True,
        "owned_workspaces": [],
        "personal_pages": 1,
        "unresolved_requests": 2,
    }
    assert reader.request("DELETE", "/v1/account", json=DELETE).status_code == 204
    assert reader.get("/v1/account/export").status_code == 401
    assert owner.get("/v1/personal-pages/" + retained["page_id"]).status_code == 200
    assert (
        owner.post("/v1/template-imports/preview", json={"code": link["code"]}).status_code == 404
    )
    with Database(settings).transaction() as db:
        for table in (
            "shared_templates",
            "personal_pages",
            "favorites",
            "favorite_state",
            "event_preferences",
            "change_outbox",
            "sessions",
            "memberships",
            "grants",
        ):
            assert not db.execute("SELECT 1 FROM " + table + " WHERE user_id=%s", (uid,)).fetchone()
        states = {
            r["action_request_id"]: r["state"]
            for r in db.execute("SELECT * FROM action_requests").fetchall()
        }
        assert states[pending["action_request_id"]] == "cancelled"
        assert states[acknowledged["action_request_id"]] == "unknown"
        assert db.execute("SELECT count(*) n FROM event_preferences").fetchone() == {"n": 1}


def test_owner_deletion_is_blocked_then_transfer_preserves_workspace_and_bot(
    settings: Settings, shop: tuple[Any, ...]
) -> None:
    owner, bot, reader, source, uid = shop
    org = owner.get("/v1/account/business-profile").json()["org_id"]
    endpoint = f"/v1/workspaces/{org}/ownership"
    preview = owner.get("/v1/account/deletion-preview").json()
    assert not preview["can_delete"] and preview["owned_workspaces"][0]["org_id"] == org
    blocked = owner.request("DELETE", "/v1/account", json=DELETE)
    assert blocked.status_code == 409 and blocked.json()["code"] == "ownership_transfer_required"
    assert owner.get("/v1/auth/session").status_code == 200
    assert bot.get("/v1/bot/identity").status_code == 200
    add(owner, org, "customer", "admin")
    queued = queue(reader, source)
    before = fill_queue(Database(settings), source["channel_id"])
    result = owner.post(endpoint, json={"username": "customer", "password": PASSWORD})
    assert result.status_code == 200 and result.json()["owner_user_id"] == uid
    validate("OwnershipTransfer", result.json())
    assert (
        owner.post(endpoint, json={"username": "customer", "password": PASSWORD}).status_code == 403
    )
    assert owner.get("/v1/account/deletion-preview").json()["can_delete"]
    assert owner.request("DELETE", "/v1/account", json=DELETE).status_code == 204
    assert bot.get("/v1/bot/identity").status_code == 200
    assert reader.get("/v1/channels/" + source["slug"]).status_code == 200
    assert (
        reader.get("/v1/action-requests/" + queued["action_request_id"]).json()["state"] == "queued"
    )
    assert reader.get("/v1/account/business-profile").json()["org_id"] == org
    with Database(settings).transaction() as db:
        assert db.execute("SELECT count(*) n FROM memberships WHERE role='owner'").fetchone() == {
            "n": 1
        }
        assert db.execute("SELECT count(*) n FROM change_outbox").fetchone() == {"n": before}


def test_transfer_rejects_unauthorized_unready_and_existing_owners(settings: Settings) -> None:
    with client(settings) as owner, client(settings) as admin, client(settings) as editor:
        register(owner, "owner")
        register(admin, "admin")
        register(editor, "editor")
        org = business(owner)
        endpoint = f"/v1/workspaces/{org}/ownership"
        add(owner, org, "admin", "admin")
        add(owner, org, "editor", "editor")
        for caller in (admin, editor):
            assert (
                caller.post(endpoint, json={"username": "owner", "password": PASSWORD}).status_code
                == 403
            )
        for username in ("owner", "editor", "missing"):
            assert (
                owner.post(endpoint, json={"username": username, "password": PASSWORD}).status_code
                == 409
            )
        assert (
            owner.post(
                endpoint, json={"username": "admin", "password": "wrong-password"}
            ).status_code
            == 403
        )
        assert (
            owner.post(
                endpoint,
                json={"username": "admin", "password": PASSWORD},
                headers={"X-CSRF-Token": "wrong"},
            ).status_code
            == 403
        )
        business(admin)
        assert (
            owner.post(endpoint, json={"username": "admin", "password": PASSWORD}).json()["code"]
            == "workspace_owner_limit"
        )
        assert owner.get("/v1/account/business-profile").json()["org_id"] == org


def test_transfer_and_recipient_deletion_serialize(settings: Settings) -> None:
    with client(settings) as owner, client(settings) as admin:
        register(owner, "owner")
        uid = register(admin, "admin")
        org = business(owner)
        add(owner, org, "admin", "admin")
        with ThreadPoolExecutor(max_workers=2) as pool:
            transfer = pool.submit(
                lambda: owner.post(
                    f"/v1/workspaces/{org}/ownership",
                    json={"username": "admin", "password": PASSWORD},
                )
            )
            deletion = pool.submit(lambda: admin.request("DELETE", "/v1/account", json=DELETE))
            result, removed = transfer.result(), deletion.result()
        assert (result.status_code, removed.status_code) in {(200, 409), (409, 204)}
        with Database(settings).transaction() as db:
            row = db.execute(
                "SELECT u.deleted_at,m.role FROM organizations o JOIN users u "
                "ON u.user_id=o.owner_user_id JOIN memberships m ON "
                "m.org_id=o.org_id AND m.user_id=o.owner_user_id WHERE o.org_id=%s",
                (org,),
            ).fetchone()
            assert row and row["deleted_at"] is None and row["role"] == "owner"
            if removed.status_code == 204:
                assert not db.execute(
                    "SELECT 1 FROM memberships WHERE user_id=%s", (uid,)
                ).fetchone()


def test_transfer_marker_failure_rolls_back_every_ownership_write(settings: Settings) -> None:
    with client(settings) as owner, client(settings) as admin:
        register(owner, "owner")
        register(admin, "admin")
        org = business(owner)
        add(owner, org, "admin", "admin")
        with Database(settings).transaction() as db:
            db.execute(
                "CREATE FUNCTION fail_marker() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                "RAISE EXCEPTION 'synthetic marker failure'; END $$"
            )
            db.execute(
                "CREATE TRIGGER fail_marker BEFORE UPDATE ON delivery_state "
                "FOR EACH ROW EXECUTE FUNCTION fail_marker()"
            )
        assert (
            owner.post(
                f"/v1/workspaces/{org}/ownership", json={"username": "admin", "password": PASSWORD}
            ).status_code
            == 500
        )
        assert owner.get("/v1/account/business-profile").json()["org_id"] == org
        assert admin.get("/v1/account/business-profile").status_code == 404
        assert {
            r["username"]: r["role"]
            for r in owner.get(f"/v1/workspaces/{org}/members").json()["items"]
        } == {"owner": "owner", "admin": "admin"}
