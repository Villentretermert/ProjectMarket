"""Durable request-only actions. GET, delivery ACK and business result are distinct."""

import asyncio
import hmac
import json
import re
import time
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from marketob_api.access import require_read
from marketob_api.auth_routes import Empty
from marketob_api.bot_identity import BotIdentity, authenticate_bot, require_bot_channel
from marketob_api.channels import Cursor, Limit, content, published_definition
from marketob_api.config import Settings
from marketob_api.cursors import Scan, decode_scan, encode_scan, session_binding, signing_key
from marketob_api.database import Connection, Database
from marketob_api.errors import ApiError
from marketob_api.identity import authenticate, digest, identifier, rate_limit
from marketob_api.payloads import validate_payload
from marketob_api.request_state import TERMINAL, event_view, notify_status, status_view


def fingerprint(body: dict[str, Any]) -> str:
    return digest(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def owned_event(connection: Connection, current: BotIdentity, event_id: str) -> dict[str, Any]:
    candidate = connection.execute(
        "SELECT channel_id FROM action_requests WHERE event_id=%s AND bot_id=%s",
        (event_id, current.bot_id),
    ).fetchone()
    if candidate is None:
        raise ApiError(404, "request_not_found", "The request is unavailable.")
    require_bot_channel(connection, current, candidate["channel_id"])
    row = connection.execute(
        "SELECT * FROM action_requests WHERE event_id=%s AND bot_id=%s FOR UPDATE",
        (event_id, current.bot_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "request_not_found", "The request is unavailable.")
    return row


def event_page(
    connection: Connection, bot_id: str, limit: int, cursor: str | None, *, unresolved: bool
) -> dict[str, Any]:
    binding = session_binding(bot_id, "unresolved" if unresolved else "events")
    if cursor:
        scan = decode_scan(connection, binding, cursor)
    else:
        maximum = connection.execute(
            "SELECT coalesce(max(sequence),0) AS upper FROM action_requests WHERE bot_id=%s",
            (bot_id,),
        ).fetchone()
        assert maximum is not None
        scan = Scan(maximum["upper"], 0, int(time.time()) + 60)
    rows = connection.execute(
        "SELECT r.* FROM action_requests r JOIN channel_access a USING(channel_id) "
        "WHERE r.bot_id=%s AND a.deleted_at IS NULL AND r.sequence>%s AND r.sequence<=%s "
        "AND r.state IN ('queued','processing','unknown') AND (%s OR r.acknowledged_at IS NULL) "
        "ORDER BY r.sequence LIMIT %s",
        (bot_id, scan.after, scan.upper, unresolved, limit + 1),
    ).fetchall()
    next_cursor = (
        encode_scan(
            connection, binding, Scan(scan.upper, rows[limit - 1]["sequence"], scan.expires)
        )
        if len(rows) > limit
        else None
    )
    return {"items": [event_view(row) for row in rows[:limit]], "next_cursor": next_cursor}


def router(settings: Settings) -> APIRouter:
    api = APIRouter(prefix="/v1", tags=["actions"])
    database = Database(settings)

    @api.post("/channels/{channel_id}/actions", status_code=202)
    def create_request(channel_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        validate_payload("ActionInput", body)
        key = request.headers.get("idempotency-key", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key):
            raise ApiError(422, "invalid_idempotency_key", "Supply a stable Idempotency-Key.")
        if body["quantity"] != 1:
            raise ApiError(422, "unsupported_quantity", "The pilot requests one item at a time.")
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            rate_limit(database, "action:" + current.user_id, settings.action_rate_limit)
            # The request's bot FK needs a key-share lock before the channel lock.
            # This keeps creation ordered with bot revoke (organization -> bot -> channel).
            organization = connection.execute(
                "SELECT o.org_id,a.bot_id FROM organizations o JOIN channel_access a USING(org_id) "
                "WHERE a.channel_id=%s AND o.active AND a.deleted_at IS NULL AND a.published "
                "FOR SHARE OF o",
                (channel_id,),
            ).fetchone()
            if organization is None:
                raise ApiError(404, "source_unavailable", "This source is unavailable.")
            active_bot = connection.execute(
                "SELECT bot_id FROM bots WHERE bot_id=%s AND org_id=%s AND state='active' "
                "FOR KEY SHARE",
                (organization["bot_id"], organization["org_id"]),
            ).fetchone()
            if active_bot is None:
                raise ApiError(404, "source_unavailable", "This source is unavailable.")
            access = require_read(connection, channel_id, current.user_id, exclusive=True)
            connection.execute(
                "DELETE FROM action_requests WHERE user_id=%s AND channel_id=%s "
                "AND idempotency_key=%s AND terminal_at<=now()-interval '30 days'",
                (current.user_id, channel_id, key),
            )
            old = connection.execute(
                "SELECT * FROM action_requests WHERE user_id=%s AND channel_id=%s "
                "AND idempotency_key=%s",
                (current.user_id, channel_id, key),
            ).fetchone()
            body_hash = fingerprint(body)
            if old:
                if old["body_hash"] != body_hash:
                    raise ApiError(
                        409, "idempotency_conflict", "This key has another request body."
                    )
                return status_view(old)
            value = published_definition(connection, content(connection, channel_id))
            action = next(
                (a for a in value["actions"] if a["action_id"] == body["action_id"]), None
            )
            if (
                action is None
                or action["resource_id"] != body["resource_id"]
                or action["kind"] != "request_purchase"
                or not any(
                    b["content_type"] == "product"
                    and b["source"]["resource_id"] == body["resource_id"]
                    and body["action_id"] in b["action_ids"]
                    for b in value["layout"]["blocks"]
                )
            ):
                raise ApiError(
                    422, "action_not_allowed", "This action is not published for this item."
                )
            source = connection.execute(
                "SELECT * FROM source_records WHERE channel_id=%s AND resource_id=%s "
                "AND NOT deleted",
                (channel_id, body["resource_id"]),
            ).fetchone()
            if (
                source is None
                or source["content_type"] != "product"
                or source["content"]["availability"] != "in_stock"
            ):
                raise ApiError(409, "resource_unavailable", "This item is unavailable.")
            if source["source_revision"] != body["observed_source_revision"]:
                raise ApiError(409, "resource_changed", "Refresh the item before requesting it.")
            actor = (
                "actor_"
                + hmac.digest(
                    signing_key(connection),
                    (access["bot_id"] + ":" + current.user_id).encode(),
                    "sha256",
                ).hex()
            )
            row = connection.execute(
                "INSERT INTO action_requests(action_request_id,event_id,channel_id,bot_id,user_id,"
                "actor_ref,resource_id,action_id,observed_source_revision,quantity,"
                "idempotency_key,body_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s) RETURNING *",
                (
                    identifier("request"),
                    identifier("event"),
                    channel_id,
                    access["bot_id"],
                    current.user_id,
                    actor,
                    body["resource_id"],
                    body["action_id"],
                    body["observed_source_revision"],
                    key,
                    body_hash,
                ),
            ).fetchone()
            assert row is not None
            notify_status(connection, row)
            return status_view(row)

    @api.get("/action-requests/{action_request_id}")
    def read_request(action_request_id: str, request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            row = connection.execute(
                "SELECT * FROM action_requests WHERE action_request_id=%s AND user_id=%s",
                (action_request_id, current.user_id),
            ).fetchone()
            if row is None:
                raise ApiError(404, "request_not_found", "The request is unavailable.")
            require_read(connection, row["channel_id"], current.user_id)
            # Refresh after the access lock: a concurrent ACK/result/revocation may have completed.
            row = connection.execute(
                "SELECT * FROM action_requests WHERE action_request_id=%s", (action_request_id,)
            ).fetchone()
            if row is None:
                raise ApiError(404, "request_not_found", "The request is unavailable.")
            return status_view(row)

    def poll_once(request: Request, limit: int, cursor: str | None, first: bool) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate_bot(connection, request, "events:read")
            if first:
                rate_limit(database, "bot-read:" + current.bot_id, settings.bot_read_rate_limit)
            return event_page(connection, current.bot_id, limit, cursor, unresolved=False)

    @api.get("/bot/events")
    async def events(
        request: Request,
        limit: Limit = 100,
        cursor: Cursor = None,
        wait: Annotated[int, Query(ge=0, le=25)] = 0,
    ) -> dict[str, Any]:
        if cursor and wait:
            raise ApiError(
                400, "invalid_query", "Long polling is available on the first page only."
            )
        deadline = time.monotonic() + wait
        first = True
        while True:
            page = await run_in_threadpool(poll_once, request, limit, cursor, first)
            if page["items"] or time.monotonic() >= deadline or await request.is_disconnected():
                return page
            first = False
            # Waiting holds no database connection, row lock or synchronous worker thread.
            await asyncio.sleep(min(1.0, max(0, deadline - time.monotonic())))

    @api.get("/bot/requests")
    def unresolved(request: Request, limit: Limit = 100, cursor: Cursor = None) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate_bot(connection, request, "events:read")
            rate_limit(database, "bot-read:" + current.bot_id, settings.bot_read_rate_limit)
            return event_page(connection, current.bot_id, limit, cursor, unresolved=True)

    @api.post("/bot/events/{event_id}/ack")
    def acknowledge(event_id: str, body: Empty, request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate_bot(connection, request, "events:ack")
            rate_limit(database, "bot-action:" + current.bot_id, settings.bot_action_rate_limit)
            row = owned_event(connection, current, event_id)
            if row["state"] == "cancelled":
                raise ApiError(
                    409, "request_cancelled", "This request was cancelled before receipt."
                )
            if row["acknowledged_at"] is None:
                acknowledged = connection.execute(
                    "UPDATE action_requests SET acknowledged_at=now() "
                    "WHERE event_id=%s RETURNING *",
                    (event_id,),
                ).fetchone()
                assert acknowledged is not None
                row = acknowledged
            return {"event_id": event_id, "acknowledged_at": row["acknowledged_at"]}

    @api.post("/bot/events/{event_id}/result")
    def result(event_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        validate_payload("Result", body)
        with database.transaction() as connection:
            current = authenticate_bot(connection, request, "events:result")
            rate_limit(database, "bot-action:" + current.bot_id, settings.bot_action_rate_limit)
            row = owned_event(connection, current, event_id)
            body_hash = fingerprint(body)
            old = connection.execute(
                "SELECT * FROM action_results WHERE bot_id=%s AND result_id=%s",
                (current.bot_id, body["result_id"]),
            ).fetchone()
            if old:
                if (
                    old["body_hash"] != body_hash
                    or old["action_request_id"] != row["action_request_id"]
                ):
                    raise ApiError(
                        409, "idempotency_conflict", "This result ID has another body or event."
                    )
                return status_view(row)
            if row["acknowledged_at"] is None:
                raise ApiError(
                    409,
                    "ack_required",
                    "Persist the event locally and ACK before reporting a result.",
                )
            if row["state"] in TERMINAL:
                raise ApiError(409, "terminal_conflict", "The terminal result is immutable.")
            if body["result_revision"] <= row["result_revision"]:
                raise ApiError(
                    409, "stale_result_revision", "Send a strictly higher result revision."
                )
            updated = connection.execute(
                "UPDATE action_requests SET state=%s,summary=%s,result_revision=%s,"
                "updated_at=now(),"
                "progress_at=now(),terminal_at=CASE WHEN %s THEN now() ELSE NULL END "
                "WHERE event_id=%s RETURNING *",
                (
                    body["state"],
                    body["summary"],
                    body["result_revision"],
                    body["state"] in TERMINAL,
                    event_id,
                ),
            ).fetchone()
            assert updated is not None
            connection.execute(
                "INSERT INTO action_results(bot_id,result_id,action_request_id,body_hash,"
                "external_reference) VALUES (%s,%s,%s,%s,%s)",
                (
                    current.bot_id,
                    body["result_id"],
                    row["action_request_id"],
                    body_hash,
                    body.get("external_reference"),
                ),
            )
            notify_status(connection, updated)
            return status_view(updated)

    return api
