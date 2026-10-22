"""Per-bot credentials. Lock organization, bot, then key for revoke/rotation ordering."""

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Request

from marketob_api.database import Connection
from marketob_api.errors import ApiError
from marketob_api.identity import digest, identifier, require_business

SCOPES = ("messages:write", "events:read", "events:ack", "events:result")


def bearer(request: Request, prefix: str) -> str:
    value = request.headers.get("authorization", "")
    if not re.fullmatch(r"Bearer " + prefix + r"_[A-Za-z0-9_-]{43}", value):
        raise ApiError(401, "invalid_credentials", "A valid bot credential is required.")
    return value[7:]


def owned_bot(connection: Connection, bot_id: str, user_id: str) -> dict[str, Any]:
    org_id = require_business(connection, user_id)
    row = connection.execute(
        "SELECT * FROM bots WHERE bot_id=%s AND org_id=%s FOR UPDATE", (bot_id, org_id)
    ).fetchone()
    if row is None:
        raise ApiError(404, "object_not_found", "The bot is unavailable.")
    return row


def bot_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in ("bot_id", "name", "state")}


def key_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: row[key] for key in ("key_id", "prefix", "scopes", "revoked")},
        "expires_at": row["expires_at"].astimezone(UTC),
    }


def registration(connection: Connection, bot: dict[str, Any]) -> dict[str, Any]:
    if bot["state"] == "revoked":
        raise ApiError(409, "bot_revoked", "Create a new bot after revocation.")
    token = "mr_" + secrets.token_urlsafe(32)
    row = connection.execute(
        "INSERT INTO bot_registrations(token_hash,bot_id,expires_at) "
        "VALUES (%s,%s,now()+interval '15 minutes') ON CONFLICT(bot_id) DO UPDATE "
        "SET token_hash=excluded.token_hash,expires_at=excluded.expires_at RETURNING expires_at",
        (digest(token), bot["bot_id"]),
    ).fetchone()
    assert row is not None
    return {
        "bot": bot_metadata(bot),
        "registration_credential": token,
        "expires_at": row["expires_at"].astimezone(UTC),
    }


def issue_key(connection: Connection, bot_id: str, scopes: list[str]) -> dict[str, Any]:
    token = "mb_" + secrets.token_urlsafe(32)
    row = connection.execute(
        "INSERT INTO bot_keys(key_id,bot_id,token_hash,prefix,scopes,expires_at) "
        "VALUES (%s,%s,%s,%s,%s,now()+interval '90 days') RETURNING *",
        (identifier("key"), bot_id, digest(token), token[:12], scopes),
    ).fetchone()
    assert row is not None
    return {"bot_id": bot_id, "key": key_metadata(row), "api_key": token}


def lock_active_bot(connection: Connection, bot_id: str, org_id: str) -> None:
    org = connection.execute(
        "SELECT 1 FROM organizations WHERE org_id=%s AND active FOR SHARE", (org_id,)
    ).fetchone()
    if org is None:
        raise ApiError(401, "invalid_credentials", "The bot credential is unavailable.")
    row = connection.execute(
        "SELECT 1 FROM bots WHERE bot_id=%s AND state='active' FOR UPDATE", (bot_id,)
    ).fetchone()
    if row is None:
        raise ApiError(401, "invalid_credentials", "The bot credential is unavailable.")


@dataclass(frozen=True)
class BotIdentity:
    bot_id: str
    org_id: str
    key_id: str
    scopes: list[str]
    expires_at: datetime


def authenticate_bot(
    connection: Connection, request: Request, scope: str | None = None
) -> BotIdentity:
    token_hash = digest(bearer(request, "mb"))
    candidate = connection.execute(
        "SELECT b.bot_id,b.org_id FROM bot_keys k JOIN bots b USING(bot_id) WHERE k.token_hash=%s",
        (token_hash,),
    ).fetchone()
    if candidate is None:
        raise ApiError(401, "invalid_credentials", "The bot credential is unavailable.")
    lock_active_bot(connection, candidate["bot_id"], candidate["org_id"])
    key = connection.execute(
        "SELECT key_id,scopes,expires_at FROM bot_keys WHERE token_hash=%s "
        "AND NOT revoked AND expires_at>now() FOR SHARE",
        (token_hash,),
    ).fetchone()
    if key is None:
        raise ApiError(401, "invalid_credentials", "The bot credential is unavailable.")
    if scope is not None and scope not in key["scopes"]:
        raise ApiError(403, "insufficient_scope", "This key does not permit this operation.")
    connection.execute("UPDATE bots SET last_seen=now() WHERE bot_id=%s", (candidate["bot_id"],))
    return BotIdentity(**candidate, **key)


def require_bot_channel(connection: Connection, current: BotIdentity, channel_id: str) -> None:
    row = connection.execute(
        "SELECT 1 FROM channel_access WHERE channel_id=%s AND bot_id=%s "
        "AND org_id=%s AND deleted_at IS NULL FOR UPDATE",
        (channel_id, current.bot_id, current.org_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "source_unavailable", "The source is unavailable.")
