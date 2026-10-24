"""Bounded local retention worker. Does not erase latest records or revision tombstones."""

import argparse
import time
from typing import TYPE_CHECKING

from marketob_api.worker_health import HEARTBEAT, healthy

if TYPE_CHECKING:
    from marketob_api.database import Database


def prune(database: Database, batch: int = 5000) -> dict[str, int]:
    with database.transaction() as connection:
        history = connection.execute(
            "DELETE FROM ingest_history WHERE receipt_id IN (SELECT receipt_id FROM ingest_history "
            "WHERE received_at<=now()-interval '30 days' ORDER BY received_at LIMIT %s "
            "FOR UPDATE SKIP LOCKED)",
            (batch,),
        ).rowcount
        receipts = connection.execute(
            "DELETE FROM message_receipts WHERE receipt_id IN "
            "(SELECT receipt_id FROM message_receipts "
            "WHERE received_at<=now()-interval '30 days' ORDER BY received_at LIMIT %s "
            "FOR UPDATE SKIP LOCKED)",
            (batch,),
        ).rowcount
    return {"history": history, "receipts": receipts}


def prune_updates(database: Database, batch: int = 5000) -> int:
    from marketob_api.updates import dispatch

    dispatch(database, batch=5000)
    with database.transaction() as connection:
        state = connection.execute("SELECT * FROM delivery_state FOR UPDATE").fetchone()
        assert state is not None
        # Delete only a contiguous prefix. Clock corrections must not remove fresh hints.
        rows = connection.execute(
            "SELECT delivery_sequence FROM change_outbox WHERE delivery_sequence < "
            "(SELECT coalesce(min(delivery_sequence),%s) FROM change_outbox "
            "WHERE delivered_at>now()-interval '1 hour') "
            "ORDER BY delivery_sequence LIMIT %s",
            (state["watermark"] + 1, batch),
        ).fetchall()
        if rows:
            floor = rows[-1]["delivery_sequence"]
            connection.execute("DELETE FROM change_outbox WHERE delivery_sequence<=%s", (floor,))
            connection.execute(
                "UPDATE delivery_state SET retention_floor=greatest(retention_floor,%s)", (floor,)
            )
        return len(rows)


def prune_private_metadata(database: Database, batch: int = 5000) -> dict[str, int]:
    """Remove unusable preferences/hints without changing delivery cursors or requests."""
    with database.transaction() as connection:
        preferences = connection.execute(
            "DELETE FROM event_preferences WHERE ctid IN (SELECT p.ctid "
            "FROM event_preferences p JOIN users u USING(user_id) "
            "JOIN channel_access a USING(channel_id) JOIN organizations o USING(org_id) "
            "WHERE u.deleted_at IS NOT NULL OR a.deleted_at IS NOT NULL OR NOT o.active "
            "ORDER BY p.sequence LIMIT %s FOR UPDATE OF p SKIP LOCKED)",
            (batch,),
        ).rowcount
        updates = connection.execute(
            "DELETE FROM change_outbox WHERE sequence IN (SELECT c.sequence "
            "FROM change_outbox c JOIN channel_access a USING(channel_id) "
            "JOIN organizations o USING(org_id) LEFT JOIN users u ON u.user_id=c.user_id "
            "WHERE u.deleted_at IS NOT NULL OR ((a.deleted_at IS NOT NULL OR NOT o.active) "
            "AND NOT (c.user_id IS NULL AND c.kind IN ('access.revoked','source.deleted') "
            "AND c.data_revision IS NULL AND c.resource_id IS NULL AND c.receipt_id IS NULL "
            "AND c.action_request_id IS NULL AND c.event_name IS NULL)) "
            "ORDER BY c.sequence LIMIT %s FOR UPDATE OF c SKIP LOCKED)",
            (batch,),
        ).rowcount
    # Keep minimal source revocation hints until normal prefix retention expires.
    # Holes are safe: delivery IDs are never reused and unrelated events remain intact.
    return {"privacy_preferences": preferences, "privacy_updates": updates}


def maintain(database: Database) -> dict[str, int]:
    from marketob_api.request_state import maintain_requests

    # Free delivery capacity before timeouts create their own status notifications.
    result = {
        "outbox": prune_updates(database),
        **prune(database),
        **maintain_requests(database),
        **prune_private_metadata(database),
    }
    with database.transaction() as connection:
        for table, column in (
            ("sessions", "expires_at"),
            ("rate_windows", "window_start"),
            ("rate_buckets", "updated_at"),
        ):
            connection.execute(
                f"DELETE FROM {table} WHERE ctid IN (SELECT ctid FROM {table} "
                f"WHERE {column}<now()-interval '1 day' LIMIT 5000 FOR UPDATE SKIP LOCKED)"
            )
        connection.execute("UPDATE worker_state SET succeeded_at=clock_timestamp()")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    if args.health:
        raise SystemExit(0 if healthy(HEARTBEAT) else 1)
    # The frequent health subprocess must not load API dependencies or compile schemas.
    import psycopg

    from marketob_api.config import Settings
    from marketob_api.database import Database
    from marketob_api.errors import ApiError
    from marketob_api.observability import LOGGER, configure_logging

    settings = Settings()
    database = Database(settings)
    configure_logging(settings.log_level, settings.log_directory, "worker")
    while True:
        try:
            result = maintain(database)
            if not args.once:
                # A failed database pass must not refresh the worker heartbeat.
                HEARTBEAT.touch()
            LOGGER.info("maintenance", extra={"event": "maintenance", **result})
        except psycopg.Error, ApiError:
            # Never log database diagnostics, DSNs or private payloads.
            LOGGER.warning("maintenance_failed", extra={"event": "maintenance_failed"})
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            return
        time.sleep(60)


if __name__ == "__main__":
    main()
