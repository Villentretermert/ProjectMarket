"""Explicit personal-data projections; no credentials or source contents enter exports."""

import time
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Request

from marketob_api.channels import Cursor, Limit
from marketob_api.config import Settings
from marketob_api.cursors import Scan, decode_scan, encode_scan, session_binding
from marketob_api.database import Database
from marketob_api.identity import authenticate

Section = Literal["profile", "favorites", "spaces", "requests", "events"]


def router(settings: Settings) -> APIRouter:
    api = APIRouter(prefix="/v1/account", tags=["privacy"])
    database = Database(settings)

    @api.get("/deletion-preview")
    def deletion_preview(request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            owned = connection.execute(
                "SELECT org_id,name FROM organizations WHERE owner_user_id=%s AND active",
                (current.user_id,),
            ).fetchall()
            counts = connection.execute(
                "SELECT (SELECT count(*) FROM personal_pages WHERE user_id=%s "
                "AND deleted_at IS NULL) "
                "AS personal_pages, (SELECT count(*) FROM action_requests WHERE user_id=%s "
                "AND terminal_at IS NULL) AS unresolved_requests",
                (current.user_id, current.user_id),
            ).fetchone()
            return {"owned_workspaces": owned, "can_delete": not owned, **(counts or {})}

    @api.get("/export")
    def export(
        request: Request, section: Section = "profile", limit: Limit = 100, cursor: Cursor = None
    ) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            next_cursor = None
            if section == "profile":
                rows = connection.execute(
                    "SELECT user_id,username,display_name,created_at FROM users WHERE user_id=%s",
                    (current.user_id,),
                ).fetchall()
            elif section == "favorites":
                # At most 100 favorites; IDs are references, never an access grant.
                rows = connection.execute(
                    "SELECT channel_id,position,seen_data,seen_template FROM favorites "
                    "WHERE user_id=%s ORDER BY position,channel_id",
                    (current.user_id,),
                ).fetchall()
            elif section == "spaces":
                # At most 20 active layouts. Undo is client-local, not account storage.
                rows = connection.execute(
                    "SELECT page_id,title,layout FROM personal_pages WHERE user_id=%s "
                    "AND deleted_at IS NULL ORDER BY sequence",
                    (current.user_id,),
                ).fetchall()
            else:
                table, projection = (
                    (
                        "action_requests",
                        "action_request_id,channel_id,resource_id,action_id,"
                        "observed_source_revision,quantity,state,created_at,updated_at,"
                        "acknowledged_at,terminal_at",
                    )
                    if section == "requests"
                    else ("event_preferences", "channel_id,events")
                )
                binding = session_binding(current.token, "export:" + section)
                maximum = connection.execute(
                    "SELECT coalesce(max(sequence),0) AS upper FROM " + table + " WHERE user_id=%s",
                    (current.user_id,),
                ).fetchone()
                assert maximum is not None
                scan = (
                    decode_scan(connection, binding, cursor)
                    if cursor
                    else Scan(maximum["upper"], 0, int(time.time()) + 600)
                )
                rows = connection.execute(
                    "SELECT sequence," + projection + " FROM " + table + " WHERE user_id=%s "
                    "AND sequence>%s AND sequence<=%s ORDER BY sequence LIMIT %s",
                    (current.user_id, scan.after, scan.upper, limit + 1),
                ).fetchall()
                if len(rows) > limit:
                    next_cursor = encode_scan(
                        connection,
                        binding,
                        Scan(scan.upper, rows[limit - 1]["sequence"], scan.expires),
                    )
                rows = [{k: v for k, v in row.items() if k != "sequence"} for row in rows[:limit]]
            return {
                "schema_version": "1.0",
                "section": section,
                "items": rows,
                "next_cursor": next_cursor,
                "exported_at": datetime.now(UTC),
            }

    return api
