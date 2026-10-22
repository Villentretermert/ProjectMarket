"""Self-service teams for existing local accounts, with an immutable pilot owner."""

import time
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import Field

from marketob_api.auth_routes import ClosedModel
from marketob_api.channels import Cursor, Limit, scan_rows
from marketob_api.config import Settings
from marketob_api.cursors import Scan, decode_scan, encode_scan, session_binding
from marketob_api.database import Database
from marketob_api.errors import ApiError
from marketob_api.identity import authenticate
from marketob_api.request_state import reconcile_access
from marketob_api.workspace_access import workspace


class MemberWrite(ClosedModel):
    role: Literal["admin", "editor"]


class UsernameMember(MemberWrite):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9_-]+$")


def router(settings: Settings) -> APIRouter:
    api = APIRouter(prefix="/v1", tags=["workspaces"])
    database = Database(settings)

    @api.get("/workspaces")
    def list_workspaces(
        request: Request, limit: Limit = 100, cursor: Cursor = None
    ) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            binding = session_binding(current.token, "workspaces")
            maximum = connection.execute(
                "SELECT coalesce(max(sequence),0) AS upper FROM memberships WHERE user_id=%s",
                (current.user_id,),
            ).fetchone()
            assert maximum is not None
            scan = (
                decode_scan(connection, binding, cursor)
                if cursor
                else Scan(maximum["upper"], 0, int(time.time()) + 60)
            )
            rows = connection.execute(
                "SELECT m.sequence,o.org_id,o.name,m.role FROM memberships m "
                "JOIN organizations o USING(org_id) WHERE m.user_id=%s AND o.active "
                "AND m.sequence>%s AND m.sequence<=%s ORDER BY m.sequence LIMIT %s",
                (current.user_id, scan.after, scan.upper, limit + 1),
            ).fetchall()
            next_cursor = (
                encode_scan(
                    connection, binding, Scan(scan.upper, rows[limit - 1]["sequence"], scan.expires)
                )
                if len(rows) > limit
                else None
            )
            return {
                "items": [{k: r[k] for k in ("org_id", "name", "role")} for r in rows[:limit]],
                "next_cursor": next_cursor,
            }

    @api.get("/workspaces/{org_id}/members")
    def list_members(
        org_id: str, request: Request, limit: Limit = 100, cursor: Cursor = None
    ) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            workspace(connection, org_id, current.user_id)
            rows, next_cursor = scan_rows(
                connection,
                "memberships",
                "org_id",
                org_id,
                session_binding(current.token, "members:" + org_id),
                cursor,
                limit,
            )
            items = []
            for row in rows:
                user = connection.execute(
                    "SELECT user_id,username,display_name FROM users "
                    "WHERE user_id=%s AND deleted_at IS NULL",
                    (row["user_id"],),
                ).fetchone()
                if user:
                    items.append({**user, "role": row["role"]})
            return {"items": items, "next_cursor": next_cursor}

    @api.put("/workspaces/{org_id}/members")
    def put_member(org_id: str, body: UsernameMember, request: Request) -> dict[str, str]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            # Target user precedes organization, matching account deactivation/grants.
            user = connection.execute(
                "SELECT user_id,username,display_name FROM users WHERE username=%s "
                "AND deleted_at IS NULL FOR SHARE",
                (body.username,),
            ).fetchone()
            org = workspace(connection, org_id, current.user_id, ("owner",), exclusive=True)
            if user is None:
                raise ApiError(404, "object_not_found", "The registered user is unavailable.")
            if user["user_id"] == org["owner_user_id"]:
                raise ApiError(
                    409, "owner_protected", "The pilot workspace owner cannot be changed."
                )
            connection.execute(
                "INSERT INTO memberships(org_id,user_id,role) VALUES (%s,%s,%s) "
                "ON CONFLICT(org_id,user_id) DO UPDATE SET role=EXCLUDED.role",
                (org_id, user["user_id"], body.role),
            )
            return {**user, "role": body.role}

    @api.delete("/workspaces/{org_id}/members/{user_id}", status_code=204)
    def remove_member(org_id: str, user_id: str, request: Request) -> None:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            connection.execute("SELECT user_id FROM users WHERE user_id=%s FOR SHARE", (user_id,))
            org = workspace(connection, org_id, current.user_id, ("owner",), exclusive=True)
            if user_id == org["owner_user_id"]:
                raise ApiError(
                    409, "owner_protected", "The pilot workspace owner cannot be removed."
                )
            removed = connection.execute(
                "DELETE FROM memberships WHERE org_id=%s AND user_id=%s RETURNING user_id",
                (org_id, user_id),
            ).fetchone()
            if removed:
                sources = connection.execute(
                    "SELECT channel_id FROM channel_access WHERE org_id=%s "
                    "ORDER BY channel_id FOR UPDATE",
                    (org_id,),
                ).fetchall()
                for source in sources:
                    reconcile_access(connection, source["channel_id"])
                    connection.execute(
                        "INSERT INTO change_outbox(channel_id,user_id,kind) "
                        "VALUES (%s,%s,'access.revoked')",
                        (source["channel_id"], user_id),
                    )

    return api
