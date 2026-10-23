"""Workspace roles, immediate revocation and tenant boundaries on real PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

import pytest
from fastapi.testclient import TestClient
from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.workspace_access import workspace

from tests.test_actions import catalog, event_path, queue
from tests.test_bots import create_bot, exchange
from tests.test_channels import edit, path, publish
from tests.test_identity import business, client, register
from tests.test_identity import settings as settings
from tests.test_ingestion import gateway as gateway
from tests.test_ingestion import message

pytestmark = pytest.mark.integration


def test_revocation_waits_for_authorized_transaction_then_denies(settings: Settings) -> None:
    with client(settings) as owner, client(settings) as member:
        register(owner, "owner")
        org = business(owner)
        user_id = register(member, "member")
        add(owner, org, "member", "editor")
        with ThreadPoolExecutor(max_workers=1) as pool:
            with Database(settings).transaction() as connection:
                assert workspace(connection, org, user_id)["role"] == "editor"
                future = pool.submit(owner.delete, f"/v1/workspaces/{org}/members/{user_id}")
                with pytest.raises(TimeoutError):
                    future.result(timeout=0.25)
            assert future.result(timeout=10).status_code == 204
        assert member.get(f"/v1/workspaces/{org}/members").status_code == 404


def add(owner: TestClient, org: str, username: str, role: str) -> dict[str, Any]:
    result = owner.put(f"/v1/workspaces/{org}/members", json={"username": username, "role": role})
    assert result.status_code == 200, result.text
    return dict(result.json())


def test_owner_protection_and_workspace_isolation(settings: Settings) -> None:
    with client(settings) as owner, client(settings) as admin, client(settings) as outsider:
        owner_id = register(owner, "owner")
        org = business(owner)
        admin_id = register(admin, "admin")
        register(outsider, "outsider")
        other = business(outsider)
        add(owner, org, "admin", "admin")
        assert [i["org_id"] for i in admin.get("/v1/workspaces").json()["items"]] == [org]
        assert admin.get(f"/v1/workspaces/{other}/members").status_code == 404
        assert (
            outsider.put(
                f"/v1/workspaces/{org}/members", json={"username": "admin", "role": "editor"}
            ).status_code
            == 404
        )
        assert (
            admin.put(
                f"/v1/workspaces/{org}/members", json={"username": "outsider", "role": "editor"}
            ).status_code
            == 403
        )
        for caller in (owner, admin):
            result = caller.delete(f"/v1/workspaces/{org}/members/{owner_id}")
            assert result.status_code == (409 if caller is owner else 403)
        assert (
            owner.put(
                f"/v1/workspaces/{org}/members", json={"username": "owner", "role": "editor"}
            ).status_code
            == 409
        )
        assert (
            owner.put(
                f"/v1/workspaces/{org}/members", json={"username": "admin", "role": "owner"}
            ).status_code
            == 422
        )
        assert owner.delete(f"/v1/workspaces/{org}/members/{admin_id}").status_code == 204
        assert admin.get("/v1/workspaces").json()["items"] == []
        assert admin.get(f"/v1/workspaces/{org}/members").status_code == 404


def test_admin_keys_editor_denial_and_workspace_cursor(settings: Settings) -> None:
    with client(settings) as owner, client(settings) as admin, client(settings) as bot:
        register(owner, "owner")
        org = business(owner)
        register(admin, "admin")
        own_org = business(admin)
        add(owner, org, "admin", "admin")
        admin.headers["X-Workspace-ID"] = org
        first = create_bot(admin)
        second = create_bot(admin)
        key = exchange(bot, first["registration_credential"])
        bot_id = first["bot"]["bot_id"]
        page = admin.get("/v1/bots?limit=1").json()
        assert page["items"][0]["bot_id"] == bot_id
        admin.headers["X-Workspace-ID"] = own_org
        assert admin.get("/v1/bots", params={"cursor": page["next_cursor"]}).status_code == 400
        assert admin.get("/v1/bots").json()["items"] == []
        rotated = admin.post(
            f"/v1/bots/{bot_id}/keys",
            json={"scopes": ["messages:write"], "replaces_key_id": key["key"]["key_id"]},
        )
        assert rotated.status_code == 201
        assert (
            bot.get(
                "/v1/bot/identity", headers={"Authorization": "Bearer " + key["api_key"]}
            ).status_code
            == 401
        )
        add(owner, org, "admin", "editor")
        admin.headers["X-Workspace-ID"] = org
        assert len(admin.get("/v1/bots").json()["items"]) == 2
        assert admin.get(f"/v1/bots/{bot_id}").status_code == 200
        for method, suffix, body in [
            ("GET", "/keys", None),
            ("POST", "/keys", {"scopes": ["messages:write"]}),
            ("POST", "/registration", {}),
            ("DELETE", "", None),
            ("DELETE", "/keys/" + rotated.json()["key"]["key_id"], None),
        ]:
            assert (
                admin.request(method, f"/v1/bots/{bot_id}" + suffix, json=body).status_code == 403
            )
        assert admin.post("/v1/bots", json={"name": "Denied"}).status_code == 403
        assert second["bot"]["state"] == "pending"


def test_editor_publication_rollback_and_access_boundaries(
    settings: Settings,
    gateway: tuple[TestClient, TestClient, dict[str, Any]],
) -> None:
    owner, bot, source = gateway
    org = owner.get("/v1/account/business-profile").json()["org_id"]
    assert bot.post("/v1/bot/messages", json=message(source)).status_code == 200
    with client(settings) as editor, client(settings) as outsider:
        editor_id = register(editor, "editor")
        outsider_id = register(outsider, "outsider")
        add(owner, org, "editor", "editor")
        editor.headers["X-Workspace-ID"] = org
        first = editor.put(path(source), json=edit(source, visibility="selected"))
        assert first.status_code == 200
        publish(editor, source)
        live = "/v1/channels/" + source["slug"]
        assert editor.get(live).status_code == 200
        assert outsider.get(live).status_code == 404
        second = edit(first.json(), visibility="selected")
        second["layout"]["theme"] = "ink"
        assert editor.put(path(source), json=second).status_code == 200
        publish(editor, source, 3)
        rollback = editor.post(
            path(source, "/rollback"),
            json={"expected_template_version": 3, "target_template_version": 2},
        )
        assert rollback.status_code == 200
        assert rollback.json()["layout"]["theme"] == "blue"
        assert (
            editor.put(path(source), json=edit(rollback.json(), visibility="public")).status_code
            == 403
        )
        assert editor.put(path(source, f"/grants/{outsider_id}"), json={}).status_code == 403
        assert editor.delete(path(source)).status_code == 403
        assert editor.get(path(source, "/resources")).status_code == 200
        assert owner.delete(f"/v1/workspaces/{org}/members/{editor_id}").status_code == 204
        assert editor.get(live).status_code == 404
        assert editor.get(path(source, "/preview")).status_code == 404
        assert (
            editor.post(path(source, "/publish"), json={"expected_template_version": 4}).status_code
            == 404
        )


def test_member_removal_preserves_explicit_read_grants(
    settings: Settings,
    gateway: tuple[TestClient, TestClient, dict[str, Any]],
) -> None:
    owner, bot, source = gateway
    org = owner.get("/v1/account/business-profile").json()["org_id"]
    assert bot.post("/v1/bot/messages", json=message(source)).status_code == 200
    assert owner.put(path(source), json=edit(source, visibility="selected")).status_code == 200
    publish(owner, source)
    with client(settings) as member:
        user_id = register(member, "member")
        add(owner, org, "member", "editor")
        assert owner.put(path(source, f"/grants/{user_id}"), json={}).status_code == 204
        assert owner.delete(f"/v1/workspaces/{org}/members/{user_id}").status_code == 204
        assert member.get("/v1/channels/" + source["slug"]).status_code == 200
        assert member.get(path(source)).status_code == 404
        assert owner.delete(path(source, f"/grants/{user_id}")).status_code == 204
        assert member.get("/v1/channels/" + source["slug"]).status_code == 404
    with Database(settings).transaction() as connection:
        rows = connection.execute(
            "SELECT kind FROM change_outbox WHERE user_id=%s", (user_id,)
        ).fetchall()
        assert sum(row["kind"] == "access.revoked" for row in rows) == 2
        assert sum(row["kind"] == "channel.changed" for row in rows) == 2


def test_team_revocation_reconciles_pending_and_acked_requests(
    settings: Settings,
    gateway: tuple[TestClient, TestClient, dict[str, Any]],
) -> None:
    owner, bot, source = gateway
    catalog(owner, bot, source)
    org = owner.get("/v1/account/business-profile").json()["org_id"]
    with client(settings) as member:
        user_id = register(member, "member")
        add(owner, org, "member", "editor")
        first = queue(member, source, "before_ack")
        second = queue(member, source, "after_ack")
        events = bot.get("/v1/bot/events").json()["items"]
        event = next(e for e in events if e["action_request_id"] == second["action_request_id"])
        assert bot.post(event_path(event, "ack"), json={}).status_code == 200
        # An unrelated grant change must not cancel an authorized member's request.
        assert owner.delete(path(source, "/grants/" + user_id)).status_code == 204
        assert (
            member.get("/v1/action-requests/" + first["action_request_id"]).json()["state"]
            == "queued"
        )
        assert owner.delete(f"/v1/workspaces/{org}/members/{user_id}").status_code == 204
        for request in (first, second):
            assert (
                member.get("/v1/action-requests/" + request["action_request_id"]).status_code == 404
            )
        with Database(settings).transaction() as connection:
            rows = connection.execute(
                "SELECT action_request_id,state FROM action_requests"
            ).fetchall()
            states = {r["action_request_id"]: r["state"] for r in rows}
            assert states[first["action_request_id"]] == "cancelled"
            assert states[second["action_request_id"]] == "unknown"


def test_editor_cannot_publish_or_restore_an_audience_change(
    settings: Settings,
    gateway: tuple[TestClient, TestClient, dict[str, Any]],
) -> None:
    owner, bot, source = gateway
    org = owner.get("/v1/account/business-profile").json()["org_id"]
    assert bot.post("/v1/bot/messages", json=message(source)).status_code == 200
    first = owner.put(path(source), json=edit(source, visibility="public")).json()
    publish(owner, source)
    second = owner.put(path(source), json=edit(first, visibility="selected")).json()
    publish(owner, source, 3)
    with client(settings) as editor:
        register(editor, "editor")
        add(owner, org, "editor", "editor")
        assert (
            editor.post(
                path(source, "/rollback"),
                json={"target_template_version": 2, "expected_template_version": 3},
            ).status_code
            == 403
        )
        assert owner.put(path(source), json=edit(second, visibility="public")).status_code == 200
        assert (
            editor.post(path(source, "/publish"), json={"expected_template_version": 4}).status_code
            == 403
        )
        assert editor.get(path(source, "/audience")).status_code == 403
