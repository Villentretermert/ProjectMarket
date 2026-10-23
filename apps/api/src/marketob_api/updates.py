"""Session-scoped foreground hints; source authorization is checked at every poll."""

import re
import time
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from psycopg.types.json import Jsonb

from marketob_api.access import require_read
from marketob_api.channels import Cursor, Limit, scan_rows
from marketob_api.config import Settings
from marketob_api.cursors import Scan, decode_scan, encode_scan, session_binding
from marketob_api.database import Connection, Database
from marketob_api.errors import ApiError
from marketob_api.identity import authenticate, digest
from marketob_api.payloads import validate_payload


def dispatch(database: Database) -> int:
    # Commit allocation before any caller locks sources. Late ingestion commits get later IDs.
    with database.transaction() as connection:
        state = connection.execute("SELECT watermark FROM delivery_state FOR UPDATE").fetchone()
        assert state is not None
        rows = connection.execute(
            "SELECT sequence FROM change_outbox WHERE delivery_sequence IS NULL "
            "ORDER BY sequence LIMIT 1000"
        ).fetchall()
        if rows:
            connection.execute(
                "UPDATE change_outbox o SET delivery_sequence=v.position+%s,"
                "delivered_at=clock_timestamp() FROM "
                "(SELECT sequence,row_number() OVER (ORDER BY sequence) AS position "
                "FROM change_outbox WHERE sequence=ANY(%s)) v WHERE o.sequence=v.sequence",
                (state["watermark"], [r["sequence"] for r in rows]),
            )
            connection.execute("UPDATE delivery_state SET watermark=watermark+%s", (len(rows),))
        return int(state["watermark"]) + len(rows)


def readable(connection: Connection, channel_id: str, user_id: str) -> bool:
    try:
        require_read(connection, channel_id, user_id)
        return True
    except ApiError as error:
        if error.status != 404:
            raise
        return False


def preference(connection: Connection, user_id: str, channel_id: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT events FROM event_preferences WHERE user_id=%s AND channel_id=%s",
        (user_id, channel_id),
    ).fetchone()
    return {"channel_id": channel_id, "events": row["events"] if row else ["request.status"]}


def router(settings: Settings) -> APIRouter:
    api = APIRouter(prefix="/v1", tags=["updates"])
    database = Database(settings)

    @api.get("/preferences/{channel_id}")
    def get_preference(channel_id: str, request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            require_read(connection, channel_id, current.user_id)
            return preference(connection, current.user_id, channel_id)

    @api.put("/preferences/{channel_id}")
    def put_preference(channel_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        validate_payload("Preference", body)
        if body["channel_id"] != channel_id:
            raise ApiError(422, "invalid_request", "Channel identifiers must match.")
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            require_read(connection, channel_id, current.user_id)
            connection.execute(
                "INSERT INTO event_preferences(user_id,channel_id,events) VALUES (%s,%s,%s) "
                "ON CONFLICT(user_id,channel_id) DO UPDATE SET events=excluded.events",
                (current.user_id, channel_id, Jsonb(body["events"])),
            )
            return body

    @api.get("/preferences")
    def list_preferences(
        request: Request, cursor: Cursor = None, limit: Limit = 100
    ) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            rows, next_cursor = scan_rows(
                connection,
                "event_preferences",
                "user_id",
                current.user_id,
                session_binding(current.token, "preferences"),
                cursor,
                limit,
            )
            items = []
            for row in sorted(rows, key=lambda r: r["channel_id"]):
                if readable(connection, row["channel_id"], current.user_id):
                    items.append({k: row[k] for k in ("channel_id", "events")})
            return {"items": items, "next_cursor": next_cursor}

    @api.get("/updates")
    def updates(
        request: Request,
        cursor: Cursor = None,
        watch: Annotated[list[str] | None, Query(max_length=50)] = None,
    ) -> dict[str, Any]:
        watched = set(watch or [])
        if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", cid) for cid in watched):
            raise ApiError(422, "invalid_request", "Channel identifiers are too long.")
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            binding = session_binding(current.token, "updates")
            scan = decode_scan(connection, binding, cursor) if cursor else None
            upper = dispatch(database)
            if scan and scan.after > upper:
                raise ApiError(410, "resync_required", "Refresh snapshots with a new cursor.")
            rows = connection.execute(
                "SELECT * FROM change_outbox WHERE delivery_sequence>%s "
                "AND delivery_sequence<=%s ORDER BY delivery_sequence LIMIT 51",
                (scan.after if scan else upper, upper),
            ).fetchall()
            # Durable references and explicit visible channels express interest, never access.
            interests = watched | {
                r["channel_id"]
                for r in connection.execute(
                    "SELECT channel_id FROM favorites WHERE user_id=%s UNION "
                    "SELECT b->'source'->>'channel_id' FROM personal_pages p, "
                    "LATERAL jsonb_array_elements(p.layout->'blocks') b "
                    "WHERE p.user_id=%s AND p.deleted_at IS NULL UNION "
                    "SELECT channel_id FROM event_preferences WHERE user_id=%s",
                    (current.user_id, current.user_id, current.user_id),
                ).fetchall()
            }
            candidates = [
                r
                for r in rows[:50]
                if (r["user_id"] is None or r["user_id"] == current.user_id)
                and (
                    r["channel_id"] in interests
                    or (r["kind"] == "request.status" and r["user_id"] == current.user_id)
                )
            ]
            allowed = {
                cid: readable(connection, cid, current.user_id)
                for cid in sorted(watched | {r["channel_id"] for r in candidates})
            }
            items: list[dict[str, Any]] = []
            revoked = set()
            for row in candidates:
                cid = row["channel_id"]
                if not allowed[cid]:
                    revoked.add(cid)
                    continue
                kind = row["kind"]
                # A stale revoke followed by restoration still means fetch current state.
                if kind == "access.revoked":
                    kind = "channel.changed"
                event = "request.status" if kind == "request.status" else row["event_name"]
                items.append(
                    {
                        "update_id": "update_" + str(row["delivery_sequence"]),
                        "kind": kind,
                        "channel_id": cid,
                        "target_id": row["action_request_id"] if kind == "request.status" else cid,
                        "revision": row["data_revision"] or 0,
                        "event_name": event,
                        "notify": event is not None
                        and event in preference(connection, current.user_id, cid)["events"],
                    }
                )
            revoked |= {cid for cid in watched if not allowed[cid]}
            for cid in sorted(revoked):
                items.append(
                    {
                        "update_id": "revoked_" + digest(cid)[:32],
                        "kind": "access.revoked",
                        "channel_id": cid,
                        "target_id": cid,
                        "revision": 0,
                        "event_name": None,
                        "notify": False,
                    }
                )
            after = rows[min(len(rows), 50) - 1]["delivery_sequence"] if rows else upper
            return {
                "items": items,
                "has_more": len(rows) > 50,
                "next_cursor": encode_scan(
                    connection, binding, Scan(upper, after, int(time.time()) + 600)
                ),
            }

    return api
