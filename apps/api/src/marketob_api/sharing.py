"""Immutable layout locators; importing copies references, never data or access rights."""

import re
import secrets
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request
from psycopg.types.json import Jsonb

from marketob_api.actions import fingerprint
from marketob_api.config import Settings
from marketob_api.database import Connection, Database
from marketob_api.errors import ApiError
from marketob_api.identity import authenticate, digest, identifier
from marketob_api.payloads import validate_payload
from marketob_api.personal_pages import lock_pages, owned, resolve, view


def creation_key(request: Request) -> str:
    key = request.headers.get("idempotency-key", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key):
        raise ApiError(422, "invalid_idempotency_key", "Supply a stable Idempotency-Key.")
    return digest(key)


def share_view(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in ("share_id", "code", "expires_at")}


def template(connection: Connection, code: str) -> dict[str, Any]:
    # Lock the share before resolving sources. Revoke/delete waits for in-flight imports.
    row = connection.execute(
        "SELECT s.* FROM shared_templates s JOIN users u USING(user_id) "
        "WHERE s.code=%s AND s.revoked_at IS NULL AND u.deleted_at IS NULL "
        "AND (s.expires_at IS NULL OR s.expires_at>now()) FOR SHARE OF s",
        (code,),
    ).fetchone()
    if row is None:
        raise ApiError(404, "template_unavailable", "This template is unavailable or expired.")
    # Stored templates are versioned input too; never interpret an unknown layout.
    validate_payload(
        "PageWrite",
        {"title": row["title"], "layout": row["layout"], "expected_template_version": 0},
    )
    return row


def router(settings: Settings) -> APIRouter:
    api = APIRouter(prefix="/v1", tags=["sharing"])
    database = Database(settings)

    @api.post("/personal-pages/{page_id}/shares", status_code=201)
    def create(page_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        validate_payload("ShareCreate", body)
        key = creation_key(request)
        body_hash = fingerprint({"page_id": page_id, **body})
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            lock_pages(connection, current.user_id)
            page = owned(connection, current.user_id, page_id)
            old = connection.execute(
                "SELECT * FROM shared_templates WHERE user_id=%s AND create_key_hash=%s",
                (current.user_id, key),
            ).fetchone()
            if old:
                if old["create_body_hash"] != body_hash or old["revoked_at"] is not None:
                    raise ApiError(
                        409, "idempotency_conflict", "This creation key is already used."
                    )
                return share_view(old)
            if body["expected_template_version"] != page["layout"]["template_version"]:
                raise ApiError(409, "template_conflict", "Reload the saved page before sharing.")
            now = datetime.now(UTC)
            expiry = (
                (datetime.fromisoformat(body["expires_at"]) if body.get("expires_at") else None)
                if "expires_at" in body
                else now + timedelta(days=30)
            )
            if expiry is not None and expiry <= now:
                raise ApiError(422, "invalid_expiry", "Choose a future expiry.")
            count = connection.execute(
                "SELECT count(*) AS n FROM shared_templates WHERE page_id=%s "
                "AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>now())",
                (page_id,),
            ).fetchone()
            assert count is not None
            if count["n"] >= 20:
                raise ApiError(409, "share_limit", "Revoke a link before creating more than 20.")
            row = connection.execute(
                "INSERT INTO shared_templates(share_id,user_id,page_id,code,title,layout,"
                "expires_at,create_key_hash,create_body_hash) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "RETURNING *",
                (
                    identifier("sh"),
                    current.user_id,
                    page_id,
                    secrets.token_urlsafe(24),
                    page["title"],
                    Jsonb(page["layout"]),
                    expiry,
                    key,
                    body_hash,
                ),
            ).fetchone()
            assert row is not None
            return share_view(row)

    @api.get("/personal-pages/{page_id}/shares")
    def listing(page_id: str, request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            owned(connection, current.user_id, page_id)
            rows = connection.execute(
                "SELECT * FROM shared_templates WHERE page_id=%s AND revoked_at IS NULL "
                "AND (expires_at IS NULL OR expires_at>now()) ORDER BY created_at,share_id",
                (page_id,),
            ).fetchall()
            return {"items": [share_view(row) for row in rows]}

    @api.delete("/shares/{share_id}", status_code=204)
    def revoke(share_id: str, request: Request) -> None:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            lock_pages(connection, current.user_id)
            connection.execute(
                "UPDATE shared_templates SET revoked_at=coalesce(revoked_at,now()) "
                "WHERE share_id=%s AND user_id=%s",
                (share_id, current.user_id),
            )

    @api.post("/template-imports/preview")
    def preview(body: dict[str, Any], request: Request) -> dict[str, Any]:
        validate_payload("ImportInput", body)
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            row = template(connection, body["code"])
            snapshot = resolve(connection, current.user_id, row)
            return {
                "title": row["title"],
                "layout": row["layout"],
                "unavailable_blocks": [
                    b["block_id"] for b in snapshot["blocks"] if not b["available"]
                ],
            }

    @api.post("/template-imports", status_code=201)
    def import_page(body: dict[str, Any], request: Request) -> dict[str, Any]:
        validate_payload("ImportInput", body)
        key, body_hash = creation_key(request), fingerprint({"import": body["code"]})
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            lock_pages(connection, current.user_id)
            old = connection.execute(
                "SELECT * FROM personal_pages WHERE user_id=%s AND create_key_hash=%s",
                (current.user_id, key),
            ).fetchone()
            # A replay recovers an existing copy, even if new imports were revoked later.
            if old:
                if old["create_body_hash"] != body_hash or old["deleted_at"] is not None:
                    raise ApiError(409, "idempotency_conflict", "This import key is already used.")
                return view(old)
            source = template(connection, body["code"])
            count = connection.execute(
                "SELECT count(*) AS n FROM personal_pages WHERE user_id=%s AND deleted_at IS NULL",
                (current.user_id,),
            ).fetchone()
            assert count is not None
            if count["n"] >= 20:
                raise ApiError(409, "page_limit", "The pilot supports up to 20 personal pages.")
            # This trusted server snapshot may retain inaccessible references as placeholders.
            # No source payload or grant is stored; every later snapshot rechecks permissions.
            resolve(connection, current.user_id, source)
            layout = deepcopy(source["layout"])
            layout["template_version"] = 1
            row = connection.execute(
                "INSERT INTO personal_pages(page_id,user_id,title,layout,"
                "create_key_hash,create_body_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s) RETURNING *",
                (
                    identifier("pg"),
                    current.user_id,
                    source["title"][:73] + " (copy)",
                    Jsonb(layout),
                    key,
                    body_hash,
                ),
            ).fetchone()
            assert row is not None
            return view(row)

    return api
