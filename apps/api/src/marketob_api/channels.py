"""Immutable layout versions, explicit publication and live authorized snapshots."""

import json
import time
from copy import deepcopy
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from psycopg import sql
from psycopg.types.json import Jsonb
from starlette.responses import JSONResponse

from marketob_api.access import require_owner, require_read
from marketob_api.access_changes import invalidate_access
from marketob_api.config import Settings
from marketob_api.cursors import Scan, decode_scan, encode_scan, session_binding
from marketob_api.database import Connection, Database
from marketob_api.errors import ApiError
from marketob_api.identity import COOKIE, authenticate, digest, rate_limit, require_business
from marketob_api.payloads import validate_payload
from marketob_api.request_state import reconcile_access
from marketob_api.workspace_access import EDITORS, MANAGERS, audience_guard

Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=1024)]


def content(connection: Connection, channel_id: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT * FROM channel_content WHERE channel_id=%s", (channel_id,)
    ).fetchone()
    if row is None:
        raise ApiError(404, "source_unavailable", "This source is unavailable.")
    return row


def definition(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": row["title"],
        "visibility": row["draft_visibility"],
        "layout": row["layout"],
        "actions": row["actions"],
    }


def channel_view(
    access: dict[str, Any], row: dict[str, Any], value: dict[str, Any]
) -> dict[str, Any]:
    # Explicit projection keeps owner IDs, grants and internal revisions out of public JSON.
    return {
        "channel_id": access["channel_id"],
        "bot_id": access["bot_id"],
        "slug": row["slug"],
        "published": access["published"],
        **value,
    }


def published_definition(connection: Connection, row: dict[str, Any]) -> dict[str, Any]:
    version = connection.execute(
        "SELECT definition FROM channel_versions WHERE channel_id=%s AND template_version=%s",
        (row["channel_id"], row["published_version"]),
    ).fetchone()
    if version is None:
        raise ApiError(404, "source_unavailable", "This source is unavailable.")
    return dict(version["definition"])


def record_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": {"channel_id": row["channel_id"], "resource_id": row["resource_id"]},
        **{key: row[key] for key in ("source_revision", "data_revision", "updated_at", "content")},
    }


def snapshot(
    connection: Connection, access: dict[str, Any], row: dict[str, Any], value: dict[str, Any]
) -> dict[str, Any]:
    bindings = {
        (block["source"]["resource_id"], block["content_type"])
        for block in value["layout"]["blocks"]
    }
    rows = connection.execute(
        "SELECT * FROM source_records WHERE channel_id=%s AND resource_id=ANY(%s) "
        "AND NOT deleted ORDER BY resource_id",
        (access["channel_id"], sorted({resource for resource, _ in bindings})),
    ).fetchall()
    return {
        "channel": channel_view(access, row, value),
        "data_revision": row["data_revision"],
        "records": [
            record_view(r) for r in rows if (r["resource_id"], r["content_type"]) in bindings
        ],
    }


def validate_bindings(
    connection: Connection, channel_id: str, value: dict[str, Any], *, publishing: bool
) -> None:
    blocks, actions = value["layout"]["blocks"], value["actions"]
    if len({b["block_id"] for b in blocks}) != len(blocks) or len(
        {a["action_id"] for a in actions}
    ) != len(actions):
        raise ApiError(422, "duplicate_identifier", "Block and action IDs must be unique.")
    action_map = {a["action_id"]: a for a in actions}
    used: set[str] = set()
    for action in actions:
        if action["kind"] != "request_purchase" or action["label"] != "Request purchase":
            raise ApiError(422, "unsupported_action", "The pilot supports Request purchase only.")
    for block in blocks:
        if block["source"]["channel_id"] != channel_id:
            raise ApiError(422, "invalid_binding", "B2B blocks must use this channel's sources.")
        for action_id in block["action_ids"]:
            action = action_map.get(action_id)
            if action is None or action["resource_id"] != block["source"]["resource_id"]:
                raise ApiError(422, "invalid_binding", "Bind actions to their product block.")
            used.add(action_id)
    if used != set(action_map):
        raise ApiError(422, "invalid_binding", "Every action must be bound to a product block.")
    if publishing:
        rows = connection.execute(
            "SELECT resource_id,content_type FROM source_records WHERE channel_id=%s "
            "AND resource_id=ANY(%s) AND NOT deleted",
            (channel_id, [b["source"]["resource_id"] for b in blocks]),
        ).fetchall()
        live = {(r["resource_id"], r["content_type"]) for r in rows}
        if any((b["source"]["resource_id"], b["content_type"]) not in live for b in blocks):
            raise ApiError(409, "source_unavailable", "Publish requires live compatible sources.")


def save_draft(connection: Connection, channel_id: str, value: dict[str, Any]) -> None:
    connection.execute(
        "UPDATE channel_content SET title=%s,draft_visibility=%s,layout=%s,actions=%s "
        "WHERE channel_id=%s",
        (
            value["title"],
            value["visibility"],
            Jsonb(value["layout"]),
            Jsonb(value["actions"]),
            channel_id,
        ),
    )
    connection.execute(
        "INSERT INTO channel_versions(channel_id,template_version,definition) VALUES (%s,%s,%s)",
        (channel_id, value["layout"]["template_version"], Jsonb(value)),
    )


def publish(
    connection: Connection, access: dict[str, Any], row: dict[str, Any], value: dict[str, Any]
) -> dict[str, Any]:
    audience_guard(access, value["visibility"], access["visibility"])
    validate_bindings(connection, access["channel_id"], value, publishing=True)
    bot = connection.execute(
        "SELECT state FROM bots WHERE bot_id=%s", (access["bot_id"],)
    ).fetchone()
    if bot is None or bot["state"] != "active":
        raise ApiError(409, "bot_unavailable", "Publish requires an active bot.")
    channel_id, version = access["channel_id"], value["layout"]["template_version"]
    if row["published_version"] == version and access["published"]:
        return channel_view(access, row, value)
    connection.execute(
        "UPDATE channel_content SET published_version=%s WHERE channel_id=%s", (version, channel_id)
    )
    connection.execute(
        "UPDATE channel_access SET published=true,visibility=%s WHERE channel_id=%s",
        (value["visibility"], channel_id),
    )
    connection.execute(
        "UPDATE channel_versions SET published_at=coalesce(published_at,now()) "
        "WHERE channel_id=%s AND template_version=%s",
        (channel_id, version),
    )
    if (
        access["published"]
        and access["visibility"] == "public"
        and value["visibility"] == "selected"
    ):
        reconcile_access(connection, channel_id)
        invalidate_access(connection)
    else:
        connection.execute(
            "INSERT INTO change_outbox(channel_id,kind,data_revision) "
            "VALUES (%s,'channel.changed',%s)",
            (channel_id, row["data_revision"]),
        )
    return channel_view({**access, "published": True}, row, value)


def version_guard(row: dict[str, Any], expected: int) -> None:
    if row["layout"]["template_version"] != expected:
        raise ApiError(409, "template_conflict", "Reload the current draft before editing.")


def scan_rows(
    connection: Connection,
    table: str,
    column: str,
    value: str,
    binding: str,
    cursor: str | None,
    limit: int,
    *,
    sequence: str = "sequence",
) -> tuple[list[dict[str, Any]], str | None]:
    # All SQL identifiers are internal constants. New records never extend a running scan.
    table_name, filter_name, sequence_name = map(sql.Identifier, (table, column, sequence))
    maximum = connection.execute(
        sql.SQL("SELECT coalesce(max({}),0) AS upper FROM {} WHERE {}=%s").format(
            sequence_name, table_name, filter_name
        ),
        (value,),
    ).fetchone()
    assert maximum is not None
    scan = (
        decode_scan(connection, binding, cursor)
        if cursor
        else Scan(maximum["upper"], 0, int(time.time()) + 60)
    )
    rows = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE {}=%s AND {}>%s AND {}<=%s ORDER BY {} LIMIT %s").format(
            table_name, filter_name, sequence_name, sequence_name, sequence_name
        ),
        (value, scan.after, scan.upper, limit + 1),
    ).fetchall()
    next_cursor = (
        encode_scan(connection, binding, Scan(scan.upper, rows[limit - 1][sequence], scan.expires))
        if len(rows) > limit
        else None
    )
    return rows[:limit], next_cursor


def router(settings: Settings) -> APIRouter:
    api = APIRouter(prefix="/v1", tags=["channels"])
    database = Database(settings)

    @api.get("/owner/channels/{channel_id}")
    def read_draft(channel_id: str, request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            access = require_owner(connection, channel_id, current.user_id)
            row = content(connection, channel_id)
            return channel_view(access, row, definition(row))

    @api.put("/owner/channels/{channel_id}")
    def replace_draft(channel_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        validate_payload("ChannelDraft", body)
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            access = require_owner(connection, channel_id, current.user_id)
            row = content(connection, channel_id)
            version_guard(row, body["expected_template_version"])
            if body["layout"]["template_version"] != body["expected_template_version"] + 1:
                raise ApiError(409, "template_conflict", "Increment the template version by one.")
            value = {key: body[key] for key in ("title", "visibility", "layout", "actions")}
            audience_guard(access, value["visibility"], row["draft_visibility"])
            validate_bindings(connection, channel_id, value, publishing=False)
            save_draft(connection, channel_id, value)
            return channel_view(access, row, value)

    @api.post("/owner/channels/{channel_id}/publish")
    def publish_draft(channel_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        validate_payload("Publish", body)
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            access = require_owner(connection, channel_id, current.user_id)
            row = content(connection, channel_id)
            version_guard(row, body["expected_template_version"])
            return publish(connection, access, row, definition(row))

    @api.post("/owner/channels/{channel_id}/rollback")
    def rollback(channel_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        validate_payload("Rollback", body)
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            access = require_owner(connection, channel_id, current.user_id)
            row = content(connection, channel_id)
            version_guard(row, body["expected_template_version"])
            old = connection.execute(
                "SELECT definition FROM channel_versions WHERE channel_id=%s "
                "AND template_version=%s AND published_at IS NOT NULL",
                (channel_id, body["target_template_version"]),
            ).fetchone()
            if old is None:
                raise ApiError(404, "version_unavailable", "Choose a previously published version.")
            value = deepcopy(old["definition"])
            audience_guard(access, value["visibility"], row["draft_visibility"])
            value["layout"]["template_version"] = row["layout"]["template_version"] + 1
            validate_payload(
                "ChannelDraft",
                {**value, "expected_template_version": body["expected_template_version"]},
            )
            save_draft(connection, channel_id, value)
            return publish(connection, access, row, value)

    @api.get("/owner/channels/{channel_id}/preview")
    def preview(channel_id: str, request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            access = require_owner(connection, channel_id, current.user_id)
            row = content(connection, channel_id)
            return snapshot(connection, access, row, definition(row))

    @api.get("/owner/channels/{channel_id}/versions")
    def versions(
        channel_id: str, request: Request, limit: Limit = 100, cursor: Cursor = None
    ) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            access = require_owner(connection, channel_id, current.user_id)
            row = content(connection, channel_id)
            rows, next_cursor = scan_rows(
                connection,
                "channel_versions",
                "channel_id",
                channel_id,
                session_binding(current.token, "versions:" + channel_id),
                cursor,
                limit,
                sequence="template_version",
            )
            return {
                "items": [
                    {
                        "channel": channel_view(
                            {
                                **access,
                                "published": r["template_version"] == row["published_version"]
                                and access["published"],
                            },
                            row,
                            r["definition"],
                        ),
                        "created_at": r["created_at"],
                        "published_at": r["published_at"],
                    }
                    for r in rows
                ],
                "next_cursor": next_cursor,
            }

    @api.get("/owner/channels/{channel_id}/resources")
    def resources(
        channel_id: str, request: Request, limit: Limit = 100, cursor: Cursor = None
    ) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            require_owner(connection, channel_id, current.user_id)
            rows, next_cursor = scan_rows(
                connection,
                "source_records",
                "channel_id",
                channel_id,
                session_binding(current.token, "resources:" + channel_id),
                cursor,
                limit,
            )
            return {
                "items": [
                    {**record_view(r), "content_type": r["content_type"]}
                    for r in rows
                    if not r["deleted"]
                ],
                "next_cursor": next_cursor,
            }

    @api.get("/owner/channels")
    def list_channels(
        request: Request, limit: Limit = 100, cursor: Cursor = None
    ) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            org_id = require_business(
                connection, current.user_id, request.headers.get("x-workspace-id"), EDITORS
            )
            binding = session_binding(current.token, "channels:" + org_id)
            maximum = connection.execute(
                "SELECT coalesce(max(sequence),0) AS upper FROM channel_content"
            ).fetchone()
            assert maximum is not None
            scan = (
                decode_scan(connection, binding, cursor)
                if cursor
                else Scan(maximum["upper"], 0, int(time.time()) + 60)
            )
            rows = connection.execute(
                "SELECT c.*,a.bot_id,a.published FROM channel_content c "
                "JOIN channel_access a USING(channel_id) "
                "WHERE a.org_id=%s AND a.deleted_at IS NULL AND c.sequence>%s AND c.sequence<=%s "
                "ORDER BY c.sequence LIMIT %s FOR SHARE OF a",
                (org_id, scan.after, scan.upper, limit + 1),
            ).fetchall()
            next_cursor = (
                encode_scan(
                    connection, binding, Scan(scan.upper, rows[limit - 1]["sequence"], scan.expires)
                )
                if len(rows) > limit
                else None
            )
            return {
                "items": [channel_view(r, r, definition(r)) for r in rows[:limit]],
                "next_cursor": next_cursor,
            }

    @api.delete("/owner/channels/{channel_id}", status_code=204)
    def delete_channel(channel_id: str, request: Request) -> None:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            access = require_owner(
                connection, channel_id, current.user_id, include_deleted=True, roles=MANAGERS
            )
            if access["deleted_at"] is not None:
                return
            connection.execute(
                "UPDATE channel_access SET deleted_at=now(),published=false WHERE channel_id=%s",
                (channel_id,),
            )
            connection.execute("DELETE FROM grants WHERE channel_id=%s", (channel_id,))
            reconcile_access(connection, channel_id, disabled=True)
            invalidate_access(connection)

    @api.get("/channels/{slug}", response_model=None)
    def read_channel(slug: str, request: Request, response: Response) -> Any:
        with database.transaction() as connection:
            current = (
                authenticate(connection, request, settings) if COOKIE in request.cookies else None
            )
            if current is None:
                rate_limit(
                    database,
                    "preview:" + digest(request.client.host if request.client else "unknown"),
                    settings.read_rate_limit,
                )
            found = connection.execute(
                "SELECT channel_id FROM channel_content WHERE slug=%s", (slug,)
            ).fetchone()
            if found is None:
                raise ApiError(404, "source_unavailable", "This source is unavailable.")
            access = require_read(
                connection, found["channel_id"], current.user_id if current else None
            )
            row = content(connection, found["channel_id"])
            result = snapshot(connection, access, row, published_definition(connection, row))
            encoded = jsonable_encoder(result)
            fingerprint = json.dumps(encoded, sort_keys=True, separators=(",", ":"))
            etag = '"' + digest((current.token if current else "anonymous") + fingerprint) + '"'
            headers = {"ETag": etag, "Vary": "Cookie, Origin"}
            # RFC 9110: authentication and normal request checks precede condition evaluation.
            candidates = [
                value.strip().removeprefix("W/")
                for value in request.headers.get("if-none-match", "").split(",")
            ]
            if etag in candidates or "*" in candidates:
                return Response(status_code=304, headers=headers)
            return JSONResponse(encoded, headers=headers)

    return api
