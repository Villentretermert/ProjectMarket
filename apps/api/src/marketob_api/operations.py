"""Local read-only operations report, shipped in Docker. Exit 0/1/2: ok/alert/unavailable."""

import argparse
import json
import math
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from pydantic import SecretStr

from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.errors import ApiError


def statistics(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "count": len(values),
        **{
            label: ordered[max(0, math.ceil(len(ordered) * p) - 1)] if ordered else None
            for label, p in (("p95_ms", 0.95), ("p99_ms", 0.99), ("max_ms", 1.0))
        },
    }


def log_metrics(directory: Path, start: str, end: str) -> dict[str, Any]:
    """Read only bounded app log files, with a bounded one-hour report window."""
    left, right = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if right - left > timedelta(hours=1) or left > right:
        raise ValueError("Use an ordered window of at most one hour")
    durations: dict[str, list[float]] = {}
    statuses: dict[str, int] = {}
    malformed = 0
    earliest: str | None = None
    for path in sorted(directory.glob("api.jsonl*")):
        if path.stat().st_size > 11 * 1024 * 1024:
            raise ValueError("Expected bounded rotated API logs")
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    at = datetime.fromisoformat(row["time"])
                    earliest = min(earliest, row["time"]) if earliest else row["time"]
                    if row.get("event") != "http" or not left <= at <= right:
                        continue
                    key = row["method"] + " " + row["route"]
                    # Only successful API observations measure service SLO, quotas separately.
                    status = str(row["status"])
                    statuses[status] = statuses.get(status, 0) + 1
                    if row["status"] < 400 and row["route"].startswith("/v1/"):
                        durations.setdefault(key, []).append(float(row["duration_ms"]))
                except ValueError, KeyError, TypeError:
                    malformed += 1
    count = sum(statuses.values())
    return {
        "start": start,
        "end": end,
        "requests": count,
        "statuses": statuses,
        "unexpected_5xx_fraction": sum(n for s, n in statuses.items() if s.startswith("5")) / count
        if count
        else None,
        "routes": {k: statistics(v) for k, v in sorted(durations.items())},
        "malformed_lines": malformed,
        "window_complete": earliest is not None and datetime.fromisoformat(earliest) <= left,
    }


def snapshot(database: Database) -> dict[str, Any]:
    with database.transaction() as connection:
        row = connection.execute(
            "SELECT (SELECT extract(epoch FROM now()-succeeded_at)::float FROM worker_state) "
            "AS worker_age_seconds, "
            "(SELECT count(*) FROM change_outbox WHERE delivery_sequence IS NULL) "
            "AS outbox_pending, "
            "(SELECT coalesce(extract(epoch FROM now()-min(created_at)),0)::float "
            "FROM change_outbox WHERE delivery_sequence IS NULL) AS outbox_lag_seconds, "
            "(SELECT count(*) FROM change_outbox) AS outbox_rows, "
            "(SELECT count(*) FROM action_requests WHERE terminal_at IS NULL) AS unresolved, "
            "(SELECT count(*) FROM action_requests WHERE state='unknown') AS unknown, "
            "(SELECT coalesce(extract(epoch FROM now()-min(created_at)),0)::float "
            "FROM action_requests WHERE terminal_at IS NULL AND acknowledged_at IS NULL) "
            "AS action_lag_seconds, "
            "(SELECT coalesce(max(greatest(rows/100000.0,bytes/268435456.0)),0)::float "
            "FROM history_usage) AS history_capacity_fraction, "
            "(SELECT coalesce(sum(bytes),0)::bigint FROM history_usage) AS history_json_bytes, "
            "(SELECT coalesce(sum(rows),0)::bigint FROM history_usage) AS history_rows, "
            "(SELECT coalesce(extract(epoch FROM now()-min(received_at)),0)::float "
            "FROM ingest_history) AS history_age_seconds, "
            "(SELECT coalesce(max(n),0)::bigint FROM (SELECT count(*) n FROM action_requests "
            "WHERE terminal_at IS NULL GROUP BY bot_id) q) AS largest_bot_queue, "
            "(SELECT coalesce(sum(pg_total_relation_size(c.oid)),0)::bigint FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() "
            "AND c.relkind='r') AS schema_bytes"
        ).fetchone()
        assert row is not None
        return dict(row)


def alerts(gauges: dict[str, Any], http: dict[str, Any] | None = None) -> list[str]:
    result = []
    if gauges["worker_age_seconds"] is None or gauges["worker_age_seconds"] > 130:
        result.append("worker_stale")
    for key, maximum, name in (
        ("outbox_lag_seconds", 120, "outbox_delayed"),
        ("outbox_pending", 16000, "outbox_capacity"),
        ("outbox_rows", 200000, "outbox_retention_capacity"),
        ("action_lag_seconds", 60, "bot_not_acknowledging"),
        ("unknown", 0, "requests_need_reconciliation"),
        ("largest_bot_queue", 800, "bot_queue_capacity"),
        ("history_capacity_fraction", 0.8, "history_capacity"),
        ("history_age_seconds", 30 * 86400 + 600, "retention_overdue"),
    ):
        if gauges[key] > maximum:
            result.append(name)
    if http:
        if (http["unexpected_5xx_fraction"] or 0) >= 0.01:
            result.append("api_errors")
        if not http["window_complete"] or http["malformed_lines"]:
            result.append("log_window_incomplete")
        for route in ("POST /v1/bot/messages", "GET /v1/channels/{slug}"):
            metric = http["routes"].get(route)
            if metric and (metric["p95_ms"] > 500 or metric["p99_ms"] > 2000):
                result.append("api_latency")
    return sorted(set(result))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-file", type=Path)
    parser.add_argument("--schema", default="public")
    parser.add_argument("--logs", type=Path)
    parser.add_argument("--minutes", type=int, choices=range(1, 61), default=5)
    parser.add_argument("--disk-path", type=Path)
    args = parser.parse_args()
    try:
        options: dict[str, Any] = {"database_schema": args.schema}
        if args.connection_file:
            options["database_url"] = SecretStr(json.loads(args.connection_file.read_text())["url"])
        gauges = snapshot(Database(Settings(**options)))
        now = datetime.now(UTC)
        http = (
            log_metrics(
                args.logs, (now - timedelta(minutes=args.minutes)).isoformat(), now.isoformat()
            )
            if args.logs
            else None
        )
        problems = alerts(gauges, http)
        if args.disk_path:
            disk = shutil.disk_usage(args.disk_path)
            gauges["disk_free_bytes"] = disk.free
            if disk.free < max(10 * 1024**3, disk.total * 0.15):
                problems.append("disk_reserve_low")
        print(
            json.dumps(
                {"time": now.isoformat(), "gauges": gauges, "http": http, "alerts": problems},
                indent=2,
            )
        )
        raise SystemExit(1 if problems else 0)
    except psycopg.Error, ApiError, OSError, ValueError, KeyError:
        print('{"alerts":["operations_unavailable"]}', file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
