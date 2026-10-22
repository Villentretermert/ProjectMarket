"""Durable receipt, snapshot and update hint are one PostgreSQL transaction."""

import json
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Request
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from marketob_api.bot_identity import authenticate_bot, owned_bot, require_bot_channel
from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.errors import ApiError
from marketob_api.identity import authenticate, digest, identifier
from marketob_api.payloads import validate_payload
from marketob_api.quotas import ingestion_quota
from marketob_api.workspace_access import EDITORS, audience_guard


def receipt(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: row[key] for key in ("message_id", "receipt_id", "data_revision")},
        "received_at": row["received_at"].astimezone(UTC),
    }


def router(settings: Settings) -> APIRouter:
    api = APIRouter(prefix="/v1", tags=["ingestion"])
    database = Database(settings)

    @api.post("/channels", status_code=201)
    def create_channel(body: dict[str, Any], request: Request) -> dict[str, Any]:
        validate_payload("ChannelCreate", body)
        body = {"visibility": "selected", **body}
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            bot = owned_bot(connection, body["bot_id"], current.user_id, EDITORS)
            audience_guard(bot, body["visibility"], "selected")
            if bot["state"] == "revoked":
                raise ApiError(409, "bot_revoked", "Create a channel for a live bot.")
            channel_id = identifier("ch")
            layout = {
                "schema_version": "1.0",
                "template_version": 1,
                "theme": "blue",
                "density": "compact",
                "blocks": [],
            }
            connection.execute(
                "INSERT INTO channel_access(channel_id,org_id,bot_id,visibility) "
                "VALUES (%s,%s,%s,%s)",
                (channel_id, bot["org_id"], bot["bot_id"], body["visibility"]),
            )
            try:
                connection.execute(
                    "INSERT INTO channel_content(channel_id,slug,title,layout,draft_visibility) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (channel_id, body["slug"], body["title"], Jsonb(layout), body["visibility"]),
                )
            except UniqueViolation:
                raise ApiError(409, "slug_unavailable", "Choose another channel slug.") from None
            connection.execute(
                "INSERT INTO channel_versions(channel_id,template_version,definition) "
                "VALUES (%s,1,%s)",
                (
                    channel_id,
                    Jsonb(
                        {
                            "title": body["title"],
                            "visibility": body["visibility"],
                            "layout": layout,
                            "actions": [],
                        }
                    ),
                ),
            )
            return {
                "channel_id": channel_id,
                **body,
                "published": False,
                "layout": layout,
                "actions": [],
            }

    @api.post("/bot/messages")
    def ingest(body: dict[str, Any], request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate_bot(connection, request, "messages:write")
            ingestion_quota(database, current.bot_id, settings)
            validate_payload("Message", body)
            channel_id = body["channel_id"]
            require_bot_channel(connection, current, channel_id)
            # Bot row lock serializes message IDs even across that bot's channels.
            connection.execute(
                "DELETE FROM message_receipts WHERE bot_id=%s AND message_id=%s "
                "AND received_at<=now()-interval '30 days'",
                (current.bot_id, body["message_id"]),
            )
            fingerprint = digest(
                json.dumps(
                    body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                )
            )
            previous = connection.execute(
                "SELECT * FROM message_receipts WHERE bot_id=%s AND message_id=%s",
                (current.bot_id, body["message_id"]),
            ).fetchone()
            if previous:
                if previous["body_hash"] != fingerprint:
                    raise ApiError(409, "idempotency_conflict", "This message ID has another body.")
                return receipt(previous)
            record = connection.execute(
                "SELECT * FROM source_records WHERE channel_id=%s AND resource_id=%s",
                (channel_id, body["resource_id"]),
            ).fetchone()
            if body["kind"] == "event":
                if record is None or record["deleted"]:
                    raise ApiError(404, "source_unavailable", "The source is unavailable.")
            elif record and body["source_revision"] <= record["source_revision"]:
                raise ApiError(
                    409, "stale_source_revision", "Send a strictly higher source revision."
                )
            revision = connection.execute(
                "UPDATE channel_content SET data_revision=data_revision+1 "
                "WHERE channel_id=%s RETURNING data_revision,clock_timestamp() AS timestamp",
                (channel_id,),
            ).fetchone()
            if revision is None:
                raise ApiError(404, "source_unavailable", "The source is unavailable.")
            data_revision, timestamp = revision["data_revision"], revision["timestamp"]
            if body["kind"] != "event":
                deleted = body["kind"] == "delete"
                content_type = None if deleted else body.get("content_type", "news")
                content = None if deleted else Jsonb(body["payload"])
                connection.execute(
                    "INSERT INTO source_records(channel_id,resource_id,source_revision,"
                    "data_revision,content_type,content,deleted,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT(channel_id,resource_id) DO UPDATE SET "
                    "source_revision=excluded.source_revision,data_revision=excluded.data_revision,"
                    "content_type=excluded.content_type,content=excluded.content,"
                    "deleted=excluded.deleted,updated_at=excluded.updated_at",
                    (
                        channel_id,
                        body["resource_id"],
                        body["source_revision"],
                        data_revision,
                        content_type,
                        content,
                        deleted,
                        timestamp,
                    ),
                )
            result = {
                "message_id": body["message_id"],
                "receipt_id": identifier("receipt"),
                "data_revision": data_revision,
                "received_at": timestamp,
            }
            connection.execute(
                "INSERT INTO message_receipts(bot_id,message_id,body_hash,receipt_id,"
                "channel_id,data_revision,received_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    current.bot_id,
                    body["message_id"],
                    fingerprint,
                    result["receipt_id"],
                    channel_id,
                    data_revision,
                    timestamp,
                ),
            )
            connection.execute(
                "INSERT INTO ingest_history(receipt_id,channel_id,bot_id,body,received_at) "
                "VALUES (%s,%s,%s,%s,%s)",
                (result["receipt_id"], channel_id, current.bot_id, Jsonb(body), timestamp),
            )
            connection.execute(
                "INSERT INTO change_outbox(channel_id,kind,data_revision,resource_id,receipt_id) "
                "VALUES (%s,'channel.changed',%s,%s,%s)",
                (channel_id, data_revision, body["resource_id"], result["receipt_id"]),
            )
            return receipt(result)

    return api
