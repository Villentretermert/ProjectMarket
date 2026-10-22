"""Durable aggregate and per-bot token buckets, replenished continuously."""

import math

from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.errors import ApiError


def ingestion_quota(database: Database, bot_id: str, settings: Settings) -> None:
    limits = [
        ("ingest:aggregate", settings.ingest_total_per_minute),
        ("ingest:bot:" + bot_id, settings.ingest_bot_per_minute),
    ]
    retry_after = 0
    with database.transaction() as connection:
        buckets = []
        # The global bucket is always locked first, then the bot bucket.
        for name, limit in limits:
            connection.execute(
                "INSERT INTO rate_buckets(bucket,tokens,updated_at) "
                "VALUES (%s,%s,clock_timestamp()) ON CONFLICT DO NOTHING",
                (name, limit),
            )
            row = connection.execute(
                "SELECT tokens,updated_at FROM rate_buckets WHERE bucket=%s FOR UPDATE", (name,)
            ).fetchone()
            assert row is not None
            buckets.append((name, limit, row))
        clock = connection.execute("SELECT clock_timestamp() AS value").fetchone()
        assert clock is not None
        now = clock["value"]
        refilled = []
        for name, limit, row in buckets:
            available = min(
                float(limit),
                row["tokens"] + max(0.0, (now - row["updated_at"]).total_seconds()) * limit / 60,
            )
            refilled.append((name, available))
            if available < 1:
                retry_after = max(retry_after, math.ceil((1 - available) * 60 / limit))
        for name, available in refilled:
            connection.execute(
                "UPDATE rate_buckets SET tokens=%s,updated_at=%s WHERE bucket=%s",
                (available - (0 if retry_after else 1), now, name),
            )
    if retry_after:
        raise ApiError(
            429,
            "rate_limited",
            "Message quota exceeded. Retry the same message later.",
            retry_after,
        )
