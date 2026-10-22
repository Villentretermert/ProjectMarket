"""Bounded local retention worker. Does not erase latest records or revision tombstones."""

import argparse
import logging
import time

import psycopg

from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.errors import ApiError

LOGGER = logging.getLogger(__name__)


def prune(database: Database, batch: int = 5000) -> dict[str, int]:
    with database.transaction() as connection:
        history = connection.execute(
            "DELETE FROM ingest_history WHERE receipt_id IN (SELECT receipt_id FROM ingest_history "
            "WHERE received_at<=now()-interval '7 days' ORDER BY received_at LIMIT %s "
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
    args = parser.parse_args()
    database = Database(Settings())
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            result = prune(database)
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
