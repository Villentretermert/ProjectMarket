"""Private declarative layouts; source data is resolved with current rights, never copied."""

import re
from typing import Any

from fastapi import APIRouter, Request
from psycopg.types.json import Jsonb

from marketob_api.access import require_read
from marketob_api.actions import fingerprint
from marketob_api.channels import (
    Cursor,
    Limit,
    content,
    published_definition,
    record_view,
    scan_rows,
)
from marketob_api.config import Settings
from marketob_api.cursors import session_binding
from marketob_api.database import Connection, Database
from marketob_api.errors import ApiError
from marketob_api.identity import authenticate, digest, identifier
from marketob_api.payloads import validate_payload


def lock_pages(connection: Connection, user_id: str) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("personal-pages:" + user_id,)
    )


def owned(connection: Connection, user_id: str, page_id: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT * FROM personal_pages WHERE user_id=%s AND page_id=%s "
        "AND deleted_at IS NULL FOR SHARE",
        (user_id, page_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "page_unavailable", "This personal page is unavailable.")
    return row


def view(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in ("page_id", "title", "layout")}


def sources(connection: Connection, user_id: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for channel_id in sorted({b["source"]["channel_id"] for b in blocks}):
        try:
            require_read(connection, channel_id, user_id)
            row = content(connection, channel_id)
            resolved[channel_id] = (row, published_definition(connection, row))
        except ApiError as error:
            if error.status != 404:
                raise
            resolved[channel_id] = None
    return resolved


def compatible(block: dict[str, Any], definition: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        b
        for b in definition["layout"]["blocks"]
        if b["source"] == block["source"] and b["content_type"] == block["content_type"]
    ]


def validate_references(
    connection: Connection,
    user_id: str,
    layout: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> None:
    blocks = layout["blocks"]
    if len({b["block_id"] for b in blocks}) != len(blocks):
        raise ApiError(422, "duplicate_identifier", "Block IDs must be unique.")
    old = {b["block_id"]: b for b in previous["blocks"]} if previous else {}
    live = sources(connection, user_id, blocks)
    for block in blocks:
        retained = old.get(block["block_id"])
        # A lost source must not prevent removing/reordering the rest of one's page.
        if retained and all(
            block[k] == retained[k] for k in ("source", "content_type", "action_ids")
        ):
            continue
        source = live[block["source"]["channel_id"]]
        bindings = compatible(block, source[1]) if source else []
        allowed = {action for b in bindings for action in b["action_ids"]}
        if not bindings or not set(block["action_ids"]).issubset(allowed):
            raise ApiError(
                404, "source_unavailable", "Choose a currently readable published block."
            )
        record = connection.execute(
            "SELECT 1 FROM source_records WHERE channel_id=%s AND resource_id=%s "
            "AND content_type=%s AND NOT deleted",
            (block["source"]["channel_id"], block["source"]["resource_id"], block["content_type"]),
        ).fetchone()
        if not record:
            raise ApiError(
                404, "source_unavailable", "Choose a currently readable published block."
            )


def resolve(connection: Connection, user_id: str, page: dict[str, Any]) -> dict[str, Any]:
    blocks = page["layout"]["blocks"]
    live = sources(connection, user_id, blocks)
    items = []
    for block in blocks:
        item: dict[str, Any] = {"block_id": block["block_id"], "available": False}
        source = live[block["source"]["channel_id"]]
        bindings = compatible(block, source[1]) if source else []
        if bindings:
            record = connection.execute(
                "SELECT * FROM source_records WHERE channel_id=%s AND resource_id=%s "
                "AND content_type=%s AND NOT deleted",
                (
                    block["source"]["channel_id"],
                    block["source"]["resource_id"],
                    block["content_type"],
                ),
            ).fetchone()
            if record:
                allowed = {action for b in bindings for action in b["action_ids"]}
                item.update(
                    available=True,
                    record=record_view(record),
                    slug=source[0]["slug"],
                    data_revision=source[0]["data_revision"],
                    actions=[
                        a
                        for a in source[1]["actions"]
                        if a["action_id"] in allowed and a["action_id"] in block["action_ids"]
                    ],
                )
        items.append(item)
    return {"page": view(page), "blocks": items}


def router(settings: Settings) -> APIRouter:
    api = APIRouter(prefix="/v1/personal-pages", tags=["personal pages"])
    database = Database(settings)

    @api.post("", status_code=201)
    def create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        validate_payload("PageWrite", body)
        key = request.headers.get("idempotency-key", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key):
            raise ApiError(422, "invalid_idempotency_key", "Supply a stable Idempotency-Key.")
        if body["expected_template_version"] != 0 or body["layout"]["template_version"] != 1:
            raise ApiError(409, "template_conflict", "Create a page at template version 1.")
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            lock_pages(connection, current.user_id)
            old = connection.execute(
                "SELECT * FROM personal_pages WHERE user_id=%s AND create_key_hash=%s",
                (current.user_id, digest(key)),
            ).fetchone()
            if old:
                if old["create_body_hash"] != fingerprint(body) or old["deleted_at"] is not None:
                    raise ApiError(
                        409, "idempotency_conflict", "This creation key is already used."
                    )
                return view(old)
            count = connection.execute(
                "SELECT count(*) AS n FROM personal_pages WHERE user_id=%s AND deleted_at IS NULL",
                (current.user_id,),
            ).fetchone()
            assert count is not None
            if count["n"] >= 20:
                raise ApiError(409, "page_limit", "The pilot supports up to 20 personal pages.")
            validate_references(connection, current.user_id, body["layout"])
            row = connection.execute(
                "INSERT INTO personal_pages(page_id,user_id,title,layout,"
                "create_key_hash,create_body_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s) RETURNING *",
                (
                    identifier("pg"),
                    current.user_id,
                    body["title"],
                    Jsonb(body["layout"]),
                    digest(key),
                    fingerprint(body),
                ),
            ).fetchone()
            assert row is not None
            return view(row)

    @api.get("")
    def pages(request: Request, limit: Limit = 100, cursor: Cursor = None) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            rows, next_cursor = scan_rows(
                connection,
                "personal_pages",
                "user_id",
                current.user_id,
                session_binding(current.token, "personal-pages"),
                cursor,
                limit,
            )
            return {
                "items": [view(row) for row in rows if row["deleted_at"] is None],
                "next_cursor": next_cursor,
            }

    @api.get("/{page_id}")
    def read(page_id: str, request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            return view(owned(connection, current.user_id, page_id))

    @api.get("/{page_id}/snapshot")
    def read_snapshot(page_id: str, request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            return resolve(connection, current.user_id, owned(connection, current.user_id, page_id))

    @api.put("/{page_id}")
    def replace(page_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        validate_payload("PageWrite", body)
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            lock_pages(connection, current.user_id)
            row = owned(connection, current.user_id, page_id)
            value = {key: body[key] for key in ("title", "layout")}
            expected = body["expected_template_version"]
            if body["layout"]["template_version"] != expected + 1:
                raise ApiError(409, "template_conflict", "Increment template version by one.")
            # Recover an acknowledged-lost replacement without overwriting a later edit.
            if row["layout"]["template_version"] == expected + 1 and all(
                row[k] == value[k] for k in value
            ):
                return view(row)
            if row["layout"]["template_version"] != expected:
                raise ApiError(
                    409,
                    "template_conflict",
                    "This page changed in another client. Reload the saved page.",
                )
            validate_references(connection, current.user_id, body["layout"], row["layout"])
            connection.execute(
                "UPDATE personal_pages SET title=%s,layout=%s WHERE page_id=%s",
                (body["title"], Jsonb(body["layout"]), page_id),
            )
            return {"page_id": page_id, **value}

    @api.delete("/{page_id}", status_code=204)
    def delete(page_id: str, request: Request) -> None:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            lock_pages(connection, current.user_id)
            connection.execute(
                "UPDATE shared_templates SET revoked_at=coalesce(revoked_at,now()) "
                "WHERE page_id=%s AND user_id=%s",
                (page_id, current.user_id),
            )
            connection.execute(
                "UPDATE personal_pages SET deleted_at=coalesce(deleted_at,now()),"
                "title='Deleted page',layout=%s WHERE page_id=%s AND user_id=%s",
                (
                    Jsonb(
                        {
                            "schema_version": "1.0",
                            "template_version": 1,
                            "theme": "blue",
                            "density": "compact",
                            "blocks": [],
                        }
                    ),
                    page_id,
                    current.user_id,
                ),
            )

    return api
