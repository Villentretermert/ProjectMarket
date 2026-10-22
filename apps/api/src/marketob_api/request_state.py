"""Shared request lifecycle used by delivery, access revocation and maintenance."""

from datetime import UTC, datetime, timedelta
from typing import Any

from marketob_api.database import Connection, Database

TERMINAL = {"confirmed", "failed", "cancelled"}
UNKNOWN = "The result is not known yet. The bot must reconcile this request."


def status_view(row: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: row[key]
        for key in (
            "action_request_id",
            "channel_id",
            "resource_id",
            "action_id",
            "state",
            "created_at",
            "updated_at",
            "summary",
        )
    }
    # Read time still shows uncertainty if the scheduled worker is unavailable.
    anchor = row["progress_at"] or row["acknowledged_at"] or row["created_at"]
    timeout = 300 if row["acknowledged_at"] else 60
    if row["state"] in {"queued", "processing"} and anchor + timedelta(
        seconds=timeout
    ) <= datetime.now(UTC):
        result.update(state="unknown", summary=UNKNOWN)
    return result


def event_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "event_id",
            "action_request_id",
            "actor_ref",
            "channel_id",
            "resource_id",
            "action_id",
            "quantity",
            "observed_source_revision",
            "created_at",
        )
    }


def notify_status(connection: Connection, row: dict[str, Any]) -> None:
    connection.execute(
        "INSERT INTO change_outbox(channel_id,user_id,kind,action_request_id) "
        "VALUES (%s,%s,'request.status',%s)",
        (row["channel_id"], row["user_id"], row["action_request_id"]),
    )


def reconcile_access(connection: Connection, channel_id: str, *, disabled: bool = False) -> None:
    # Caller owns the channel lock. ACK takes the same lock before acknowledging.
    rows = connection.execute(
        "UPDATE action_requests r SET state=CASE WHEN %s OR acknowledged_at IS NOT NULL "
        "THEN 'unknown' ELSE 'cancelled' END, "
        "terminal_at=CASE WHEN NOT %s AND acknowledged_at IS NULL THEN now() ELSE NULL END, "
        "updated_at=now(),summary=CASE WHEN %s OR acknowledged_at IS NOT NULL THEN %s "
        "ELSE 'Request cancelled because source access was removed.' END "
        "WHERE r.channel_id=%s AND r.state IN ('queued','processing','unknown') AND (%s OR "
        "NOT EXISTS (SELECT 1 FROM channel_access a JOIN organizations o USING(org_id) "
        "JOIN users u ON u.user_id=r.user_id WHERE a.channel_id=r.channel_id "
        "AND u.deleted_at IS NULL AND a.deleted_at IS NULL AND a.published AND o.active "
        "AND (a.visibility='public' OR o.owner_user_id=u.user_id OR EXISTS "
        "(SELECT 1 FROM grants g WHERE g.channel_id=a.channel_id AND g.user_id=u.user_id)))) "
        "RETURNING r.*",
        (disabled, disabled, disabled, UNKNOWN, channel_id, disabled),
    ).fetchall()
    for row in rows:
        notify_status(connection, row)


def reconcile_user(connection: Connection, user_id: str) -> None:
    rows = connection.execute(
        "SELECT DISTINCT channel_id FROM action_requests WHERE user_id=%s "
        "AND state IN ('queued','processing','unknown') ORDER BY channel_id",
        (user_id,),
    ).fetchall()
    for row in rows:
        access = connection.execute(
            "SELECT deleted_at FROM channel_access WHERE channel_id=%s FOR UPDATE",
            (row["channel_id"],),
        ).fetchone()
        assert access is not None
        reconcile_access(connection, row["channel_id"], disabled=access["deleted_at"] is not None)


TIMEOUT_SQL = (
    "state IN ('queued','processing') AND ((acknowledged_at IS NULL "
    "AND created_at<=now()-interval '60 seconds') OR (acknowledged_at IS NOT NULL "
    "AND coalesce(progress_at,acknowledged_at)<=now()-interval '5 minutes'))"
)


def maintain_requests(database: Database, batch: int = 5000) -> dict[str, int]:
    with database.transaction() as connection:
        candidates = connection.execute(
            "SELECT channel_id FROM action_requests WHERE "
            + TIMEOUT_SQL
            + " ORDER BY sequence LIMIT %s",
            (batch,),
        ).fetchall()
    changed = 0
    # One channel per transaction avoids taking request/FK locks before the channel lock.
    for channel_id in sorted({r["channel_id"] for r in candidates}):
        with database.transaction() as connection:
            access = connection.execute(
                "SELECT 1 FROM channel_access WHERE channel_id=%s FOR UPDATE SKIP LOCKED",
                (channel_id,),
            ).fetchone()
            if access is None:
                continue
            rows = connection.execute(
                "UPDATE action_requests SET state='unknown',summary=%s,updated_at=now() "
                "WHERE action_request_id IN (SELECT action_request_id FROM action_requests "
                "WHERE channel_id=%s AND "
                + TIMEOUT_SQL
                + " ORDER BY sequence LIMIT %s FOR UPDATE SKIP LOCKED) RETURNING *",
                (UNKNOWN, channel_id, batch - changed),
            ).fetchall()
            for row in rows:
                notify_status(connection, row)
            changed += len(rows)
    with database.transaction() as connection:
        removed = connection.execute(
            "DELETE FROM action_requests WHERE action_request_id IN "
            "(SELECT action_request_id FROM action_requests "
            "WHERE terminal_at<=now()-interval '30 days' ORDER BY terminal_at "
            "LIMIT %s FOR UPDATE SKIP LOCKED)",
            (batch,),
        ).rowcount
    return {"unknown": changed, "requests": removed}
