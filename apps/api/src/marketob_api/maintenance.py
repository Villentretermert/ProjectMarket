"""Bounded local retention worker. Does not erase latest records or revision tombstones."""

import argparse
import logging
import tempfile
import time
from pathlib import Path

import psycopg

from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.errors import ApiError

LOGGER = logging.getLogger(__name__)
HEARTBEAT = Path(tempfile.gettempdir()) / "marketob-maintenance-heartbeat"


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    if args.health:
        try:
            age = time.time() - HEARTBEAT.stat().st_mtime
        except OSError:
            raise SystemExit(1) from None
        raise SystemExit(0 if 0 <= age <= 130 else 1)
    database = Database(Settings())
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            result = prune(database)
            if not args.once:
                # A failed database pass must not refresh the worker heartbeat.
                HEARTBEAT.touch()
            if args.once or any(result.values()):
                LOGGER.info(
                    "Retention removed history=%d receipts=%d",
                    result["history"],
                    result["receipts"],
                )
        except psycopg.Error, ApiError:
            # Never log database diagnostics, DSNs or private payloads.
            LOGGER.warning("Retention storage unavailable; will retry")
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            return
        time.sleep(60)


if __name__ == "__main__":
    main()
