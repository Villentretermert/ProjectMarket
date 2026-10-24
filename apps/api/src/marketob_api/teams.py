"""Self-service teams and password-confirmed ownership transfer to an existing Admin."""

import time
from typing import Any, Literal

from fastapi import APIRouter, Request
from psycopg.errors import UniqueViolation
from pydantic import Field

from marketob_api.access_changes import invalidate_access
from marketob_api.auth_routes import ClosedModel, ConfirmPassword
from marketob_api.channels import Cursor, Limit, scan_rows
from marketob_api.config import Settings
from marketob_api.cursors import Scan, decode_scan, encode_scan, session_binding
from marketob_api.database import Database
from marketob_api.errors import ApiError
from marketob_api.identity import authenticate, digest, rate_limit, request_origin, verify_password
from marketob_api.request_state import reconcile_access
from marketob_api.workspace_access import workspace


class MemberWrite(ClosedModel):
    role: Literal["admin", "editor"]


class UsernameMember(MemberWrite):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9_-]+$")


class TransferOwnership(ConfirmPassword):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9_-]+$")


def router(settings: Settings) -> APIRouter:
    api = APIRouter(prefix="/v1", tags=["workspaces"])
    database = Database(settings)

    @api.post("/workspaces/{org_id}/ownership")
    def transfer_ownership(
        org_id: str, body: TransferOwnership, request: Request
    ) -> dict[str, str]:
        request_origin(request, settings, unsafe=True)
        peer = request.client.host if request.client else "unknown"
        rate_limit(database, "auth:" + digest(peer), settings.auth_rate_limit)
        try:
            with database.transaction() as connection:
                current = authenticate(connection, request, settings)
                user = connection.execute(
                    "SELECT password_hash FROM users WHERE user_id=%s FOR NO KEY UPDATE",
                    (current.user_id,),
                ).fetchone()
                assert user is not None
                if not verify_password(user["password_hash"], body.password.get_secret_value()):
                    raise ApiError(
                        403, "password_confirmation_failed", "Password verification failed."
                    )
                # The recipient lock serializes transfer with deletion/business-profile creation.
                target = connection.execute(
                    "SELECT user_id FROM users WHERE username=%s AND deleted_at IS NULL "
                    "FOR NO KEY UPDATE",
                    (body.username,),
                ).fetchone()
                workspace(connection, org_id, current.user_id, ("owner",), exclusive=True)
                if target is None or target["user_id"] == current.user_id:
                    raise ApiError(409, "transfer_target_invalid", "Choose another active Admin.")
                member = connection.execute(
                    "SELECT role FROM memberships WHERE org_id=%s AND user_id=%s",
                    (org_id, target["user_id"]),
                ).fetchone()
                if not member or member["role"] != "admin":
                    raise ApiError(409, "transfer_target_invalid", "Choose another active Admin.")
                # Preserve the existing one-owned-workspace limit, including legacy tombstones.
                if connection.execute(
                    "SELECT 1 FROM organizations WHERE owner_user_id=%s",
                    (target["user_id"],),
                ).fetchone():
                    raise ApiError(
                        409, "workspace_owner_limit", "This Admin already owns a workspace."
                    )
                connection.execute(
                    "UPDATE memberships SET role='admin' WHERE org_id=%s AND user_id=%s",
                    (org_id, current.user_id),
                )
                connection.execute(
                    "UPDATE memberships SET role='owner' WHERE org_id=%s AND user_id=%s",
                    (org_id, target["user_id"]),
                )
                connection.execute(
                    "UPDATE organizations SET owner_user_id=%s WHERE org_id=%s",
                    (target["user_id"], org_id),
                )
                invalidate_access(connection)
                return {"org_id": org_id, "owner_user_id": target["user_id"], "role": "admin"}
        except UniqueViolation:
            raise ApiError(
                409, "workspace_owner_limit", "This Admin already owns a workspace."
            ) from None

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
                    409, "owner_protected", "Use ownership transfer to change the workspace owner."
                )
            changed = connection.execute(
                "INSERT INTO memberships(org_id,user_id,role) VALUES (%s,%s,%s) "
                "ON CONFLICT(org_id,user_id) DO UPDATE SET role=EXCLUDED.role "
                "WHERE memberships.role IS DISTINCT FROM EXCLUDED.role RETURNING user_id",
                (org_id, user["user_id"], body.role),
            ).fetchone()
            # An exact replay has no access change and must not generate more notifications.
            if changed is None:
                return {**user, "role": body.role}
            invalidate_access(connection)
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
                invalidate_access(connection)

    return api
