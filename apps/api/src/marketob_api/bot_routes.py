"""Self-service registry and one-time credentials; all secrets are issuance-only."""

import time
from datetime import UTC
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from psycopg import sql
from pydantic import Field, field_validator

from marketob_api.auth_routes import ClosedModel, Empty
from marketob_api.bot_identity import (
    SCOPES,
    authenticate_bot,
    bearer,
    bot_metadata,
    issue_key,
    key_metadata,
    owned_bot,
    registration,
)
from marketob_api.config import Settings
from marketob_api.cursors import Scan, decode_scan, encode_scan, session_binding
from marketob_api.database import Connection, Database
from marketob_api.errors import ApiError
from marketob_api.identity import authenticate, digest, identifier, rate_limit, require_business
from marketob_api.request_state import reconcile_access


class BotCreate(ClosedModel):
    name: str = Field(min_length=1, max_length=80)


class KeyIssue(ClosedModel):
    scopes: list[Literal["messages:write", "events:read", "events:ack", "events:result"]] = Field(
        min_length=1, max_length=4
    )
    replaces_key_id: str | None = Field(
        default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
    )

    @field_validator("replaces_key_id", mode="before")
    @classmethod
    def nonnull_replacement(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("Omit the field when no key is replaced")
        return value

    @field_validator("scopes")
    @classmethod
    def unique_scopes(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Scopes must be unique")
        return values


def inventory(
    connection: Connection,
    table: str,
    column: str,
    value: str,
    binding: str,
    cursor: str | None,
    limit: int,
) -> dict[str, Any]:
    # Identifiers are server constants, never request-controlled table names.
    table_name, filter_name = sql.Identifier(table), sql.Identifier(column)
    if cursor:
        scan = decode_scan(connection, binding, cursor)
    else:
        maximum = connection.execute(
            sql.SQL("SELECT coalesce(max(sequence),0) AS upper FROM {} WHERE {}=%s").format(
                table_name, filter_name
            ),
            (value,),
        ).fetchone()
        assert maximum is not None
        scan = Scan(maximum["upper"], 0, int(time.time()) + 60)
    rows = connection.execute(
        sql.SQL(
            "SELECT * FROM {} WHERE {}=%s AND sequence>%s AND sequence<=%s "
            "ORDER BY sequence LIMIT %s"
        ).format(table_name, filter_name),
        (value, scan.after, scan.upper, limit + 1),
    ).fetchall()
    next_cursor = None
    if len(rows) > limit:
        next_cursor = encode_scan(
            connection, binding, Scan(scan.upper, rows[limit - 1]["sequence"], scan.expires)
        )
    serialize = bot_metadata if table == "bots" else key_metadata
    return {"items": [serialize(row) for row in rows[:limit]], "next_cursor": next_cursor}


def router(settings: Settings) -> APIRouter:
    api = APIRouter(prefix="/v1", tags=["bots"])
    database = Database(settings)

    @api.post("/bots", status_code=201)
    def create_bot(body: BotCreate, request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            org_id = require_business(connection, current.user_id)
            row = connection.execute(
                "INSERT INTO bots(bot_id,org_id,name) VALUES (%s,%s,%s) RETURNING *",
                (identifier("bot"), org_id, body.name),
            ).fetchone()
            assert row is not None
            return registration(connection, row)

    @api.get("/bots")
    def list_bots(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
    ) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            org_id = require_business(connection, current.user_id)
            return inventory(
                connection,
                "bots",
                "org_id",
                org_id,
                session_binding(current.token, "bots"),
                cursor,
                limit,
            )

    @api.get("/bots/{bot_id}")
    def read_bot(bot_id: str, request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            bot = owned_bot(connection, bot_id, current.user_id)
            return {
                **bot_metadata(bot),
                "last_seen": bot["last_seen"].astimezone(UTC) if bot["last_seen"] else None,
            }

    @api.post("/bots/{bot_id}/registration", status_code=201)
    def renew(bot_id: str, body: Empty, request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            return registration(connection, owned_bot(connection, bot_id, current.user_id))

    @api.post("/bot-registrations/exchange", status_code=201)
    def exchange(body: Empty, request: Request) -> dict[str, Any]:
        peer = request.client.host if request.client else "unknown"
        rate_limit(database, "bootstrap:" + digest(peer), settings.auth_rate_limit)
        token_hash = digest(bearer(request, "mr"))
        with database.transaction() as connection:
            candidate = connection.execute(
                "SELECT b.bot_id,b.org_id FROM bot_registrations r JOIN bots b USING(bot_id) "
                "WHERE r.token_hash=%s",
                (token_hash,),
            ).fetchone()
            if candidate is None:
                raise ApiError(
                    401, "invalid_credentials", "The registration credential is unavailable."
                )
            org = connection.execute(
                "SELECT 1 FROM organizations WHERE org_id=%s AND active FOR SHARE",
                (candidate["org_id"],),
            ).fetchone()
            bot = connection.execute(
                "SELECT 1 FROM bots WHERE bot_id=%s AND state!='revoked' FOR UPDATE",
                (candidate["bot_id"],),
            ).fetchone()
            if not org or not bot:
                raise ApiError(
                    401, "invalid_credentials", "The registration credential is unavailable."
                )
            consumed = connection.execute(
                "DELETE FROM bot_registrations WHERE token_hash=%s AND expires_at>now() "
                "RETURNING bot_id",
                (token_hash,),
            ).fetchone()
            if consumed is None:
                raise ApiError(
                    401, "invalid_credentials", "The registration credential is unavailable."
                )
            connection.execute(
                "UPDATE bots SET state='active' WHERE bot_id=%s", (candidate["bot_id"],)
            )
            return issue_key(connection, candidate["bot_id"], list(SCOPES))

    @api.post("/bots/{bot_id}/keys", status_code=201)
    def create_key(bot_id: str, body: KeyIssue, request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            bot = owned_bot(connection, bot_id, current.user_id)
            if bot["state"] != "active":
                raise ApiError(409, "bot_not_active", "Exchange registration before issuing keys.")
            if body.replaces_key_id:
                old = connection.execute(
                    "UPDATE bot_keys SET revoked=true WHERE key_id=%s AND bot_id=%s "
                    "RETURNING key_id",
                    (body.replaces_key_id, bot_id),
                ).fetchone()
                if old is None:
                    raise ApiError(404, "object_not_found", "The key is unavailable.")
            return issue_key(connection, bot_id, list(body.scopes))

    @api.get("/bots/{bot_id}/keys")
    def list_keys(
        bot_id: str,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
    ) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            owned_bot(connection, bot_id, current.user_id)
            return inventory(
                connection,
                "bot_keys",
                "bot_id",
                bot_id,
                session_binding(current.token, "keys:" + bot_id),
                cursor,
                limit,
            )

    @api.delete("/bots/{bot_id}/keys/{key_id}", status_code=204)
    def revoke_key(bot_id: str, key_id: str, request: Request) -> None:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            owned_bot(connection, bot_id, current.user_id)
            row = connection.execute(
                "UPDATE bot_keys SET revoked=true WHERE bot_id=%s AND key_id=%s RETURNING key_id",
                (bot_id, key_id),
            ).fetchone()
            if row is None:
                raise ApiError(404, "object_not_found", "The key is unavailable.")

    @api.delete("/bots/{bot_id}", status_code=204)
    def revoke_bot(bot_id: str, request: Request) -> None:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            bot = owned_bot(connection, bot_id, current.user_id)
            if bot["state"] == "revoked":
                return
            connection.execute("UPDATE bots SET state='revoked' WHERE bot_id=%s", (bot_id,))
            connection.execute("DELETE FROM bot_registrations WHERE bot_id=%s", (bot_id,))
            connection.execute("UPDATE bot_keys SET revoked=true WHERE bot_id=%s", (bot_id,))
            connection.execute(
                "INSERT INTO change_outbox(channel_id,kind) "
                "SELECT channel_id,'access.revoked' FROM channel_access WHERE bot_id=%s",
                (bot_id,),
            )
            connection.execute(
                "UPDATE channel_access SET deleted_at=now(),published=false WHERE bot_id=%s",
                (bot_id,),
            )
            channels = connection.execute(
                "SELECT channel_id FROM channel_access WHERE bot_id=%s", (bot_id,)
            ).fetchall()
            for source in channels:
                reconcile_access(connection, source["channel_id"], disabled=True)

    @api.get("/bot/identity")
    def bot_identity(request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate_bot(connection, request)
            rate_limit(database, "bot-read:" + current.bot_id, settings.bot_read_rate_limit)
            return {
                "bot_id": current.bot_id,
                "key_id": current.key_id,
                "scopes": current.scopes,
                "expires_at": current.expires_at.astimezone(UTC),
            }

    return api
