"""Paced API baseline, without automatic retries or claims about UI/30-minute L2."""

import argparse
import json
import math
import os
import platform
import secrets
import subprocess
import time
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

from marketob_sdk import APIError, BotClient, TransportError

from scripts.backend_lab import Lab
from scripts.smoke_ingestion import Http


def stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        return {}
    return {
        name: round(ordered[max(0, math.ceil(len(ordered) * q) - 1)] * 1000, 2)
        for name, q in [("p50_ms", 0.5), ("p95_ms", 0.95), ("p99_ms", 0.99), ("max_ms", 1)]
    }


def register(origin: str) -> Http:
    client = Http(origin)
    client.csrf = client.call(
        "POST",
        "/v1/auth/register",
        {
            "username": "load_" + uuid4().hex[:16],
            "password": secrets.token_urlsafe(24),
            "display_name": "Synthetic load client",
        },
        expected=201,
    )["csrf_token"]
    return client


def payload(index: int) -> tuple[str, dict[str, Any]]:
    match index % 5:
        case 0 | 1:
            return "news", {"title": "Synthetic load news", "body": "x" * 3000}
        case 2 | 3:
            return "product", {
                "title": "Synthetic load product",
                "description": "x" * 2900,
                "price": {"amount_minor": 250, "currency": "EUR"},
                "availability": "in_stock",
            }
        case _:
            return "chart", {
                "title": "Synthetic load chart",
                "x_label": "Sample",
                "x_kind": "number",
                "y_label": "Count",
                "unit": "items",
                "series": [
                    {
                        "name": "Series " + str(n),
                        "points": [{"x": x, "y": round(x * 1.234567 + n, 6)} for x in range(250)],
                    }
                    for n in range(4)
                ],
            }


def provision_load(lab: Lab, count: int) -> tuple[Http, list[dict[str, Any]]]:
    owner = register(lab.origin)
    owner.call("PUT", "/v1/account/business-profile", {"name": "Synthetic load workspace"})
    bots = []
    for index in range(count):
        registered = owner.call(
            "POST", "/v1/bots", {"name": "Load bot " + str(index)}, expected=201
        )
        issued = BotClient(lab.origin).exchange_registration(registered["registration_credential"])
        source = owner.call(
            "POST",
            "/v1/channels",
            {
                "bot_id": issued["bot_id"],
                "title": "Synthetic load channel",
                "slug": "load-" + uuid4().hex,
                "visibility": "public",
            },
            expected=201,
        )
        client = BotClient(lab.origin, issued["api_key"], attempts=1)
        kind, content = payload(index)
        message = {
            "schema_version": "1.0",
            "message_id": "seed_" + str(index),
            "channel_id": source["channel_id"],
            "resource_id": "load",
            "source_revision": 1,
            "occurred_at": datetime.now(UTC).isoformat(),
            "kind": "data",
            "content_type": kind,
            "payload": content,
        }
        client.send_message(message)
        route = "/v1/owner/channels/" + source["channel_id"]
        owner.call(
            "PUT",
            route,
            {
                "title": source["title"],
                "visibility": "public",
                "expected_template_version": 1,
                "layout": {
                    **source["layout"],
                    "template_version": 2,
                    "blocks": [
                        {
                            "block_id": "load",
                            "source": {"channel_id": source["channel_id"], "resource_id": "load"},
                            "content_type": kind,
                            "view": {"news": "compact", "product": "card", "chart": "line"}[kind],
                            "action_ids": [],
                        }
                    ],
                },
                "actions": [],
            },
        )
        owner.call("POST", route + "/publish", {"expected_template_version": 2})
        bots.append({"client": client, "message": message, "slug": source["slug"]})
        if (index + 1) % 20 == 0:
            print(f"Provisioned {index + 1} independent bot identities", flush=True)
    return owner, bots


def measure(lab: Lab, seconds: int, count: int, reader_count: int, rate: int) -> dict[str, Any]:
    owner, bots = provision_load(lab, count)
    readers = [register(lab.origin) for _ in range(reader_count)]
    total = seconds * rate // 60
    stop = Event()
    read_results: list[tuple[str, float]] = []

    def read_loop(index: int) -> None:
        client, n = readers[index], index
        while not stop.wait(1):
            started = time.perf_counter()
            try:
                snapshot = client.call("GET", "/v1/channels/" + bots[n % count]["slug"])
                assert len(snapshot["records"]) == 1
                status = "200"
            except Exception:
                status = "error"
            read_results.append((status, time.perf_counter() - started))
            n += 1

    def send(index: int, scheduled: float) -> dict[str, Any]:
        bot = bots[index % count]
        body = {
            **bot["message"],
            "message_id": "load_" + str(index),
            "source_revision": index // count + 2,
        }
        start = time.perf_counter()
        receipt = None
        try:
            receipt = bot["client"].send_message(body)
            status = "200"
        except APIError as error:
            status = str(error.status)
        except TransportError:
            status = "transport_error"
        elapsed = time.perf_counter() - start
        return {
            "index": index,
            "status": status,
            "duration": elapsed,
            "schedule_lag": start - scheduled,
            "receipt": receipt,
            "body": body,
        }

    initial_bytes = lab.query(
        "SELECT sum(pg_total_relation_size(c.oid)) AS n FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=current_schema() AND c.relkind='r'"
    )[0]["n"]
    lab.start("worker")
    futures: list[Future[dict[str, Any]]] = []
    reading = ThreadPoolExecutor(max_workers=max(1, reader_count))
    try:
        with ThreadPoolExecutor(max_workers=16) as writing:
            read_futures = [reading.submit(read_loop, i) for i in range(reader_count)]
            start = time.perf_counter()
            for index in range(total):
                scheduled = start + index * 60 / rate
                time.sleep(max(0, scheduled - time.perf_counter()))
                futures.append(writing.submit(send, index, scheduled))
                if index and index % rate == 0:
                    print(f"Paced load: scheduled {index} messages", flush=True)
            results = [future.result(timeout=60) for future in futures]
            time.sleep(max(0, start + seconds - time.perf_counter()))
            elapsed = time.perf_counter() - start
            stop.set()
            for future in read_futures:
                future.result(timeout=30)
    finally:
        stop.set()
        reading.shutdown(wait=True)
        lab.stop("worker")
    counts = Counter(r["status"] for r in results)
    accepted = [r for r in results if r["status"] == "200"]
    lab.stop("api")
    lab.start("api")
    receipt_ids = [r["receipt"]["receipt_id"] for r in accepted]
    durable = lab.query(
        "SELECT count(*) AS n FROM message_receipts WHERE receipt_id=ANY(%s)", (receipt_ids,)
    )[0]["n"]
    outbox = lab.query(
        "SELECT count(DISTINCT receipt_id) AS n FROM change_outbox WHERE receipt_id=ANY(%s)",
        (receipt_ids,),
    )[0]["n"]
    assert durable == outbox == len(accepted)
    for record in accepted[: min(20, len(accepted))]:
        bot = bots[record["index"] % count]
        assert bot["client"].send_message(record["body"]) == record["receipt"]
    # Verify last accepted source revisions, including streams with rejected attempts.
    latest: dict[int, dict[str, Any]] = {}
    for record in accepted:
        latest[record["index"] % count] = record
    for index, record in latest.items():
        snapshot = owner.call("GET", "/v1/channels/" + bots[index]["slug"])
        assert snapshot["records"][0]["source_revision"] == record["body"]["source_revision"]
    final_bytes = lab.query(
        "SELECT sum(pg_total_relation_size(c.oid)) AS n FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=current_schema() AND c.relkind='r'"
    )[0]["n"]
    sizes = [len(json.dumps(b["message"], separators=(",", ":")).encode()) for b in bots]
    return {
        "result": "PASS"
        if counts == {"200": total} and all(r[0] == "200" for r in read_results)
        else "FAILED",
        "profile": "API baseline; not full L2, no UI",
        "seconds": seconds,
        "elapsed_seconds": round(elapsed, 3),
        "bots": count,
        "read_sessions": reader_count,
        "writer_threads": 16,
        "target_messages_per_minute": rate,
        "scheduled": total,
        "status_counts": dict(counts),
        "successful_messages_per_minute": round(len(accepted) * 60 / elapsed, 2),
        "successful_ingest_latency": stats([r["duration"] for r in accepted]),
        "schedule_lag": stats([r["schedule_lag"] for r in results]),
        "reads": dict(Counter(r[0] for r in read_results)),
        "read_http_latency": stats([r[1] for r in read_results if r[0] == "200"]),
        "message_bytes_min_max": [min(sizes), max(sizes)],
        "content_mix": "40% news, 40% product, 20% chart",
        "durable_receipts_after_restart": durable,
        "outbox_receipts_after_restart": outbox,
        "last_source_revisions_verified": len(latest),
        "schema_bytes_before_after": [int(initial_bytes), int(final_bytes)],
        "python": platform.python_version(),
        "os": platform.platform(),
        "logical_cpus": os.cpu_count(),
        "postgres": lab.query("SHOW server_version")[0]["server_version"],
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "test_only_overrides": {"auth_rate_limit": 1000, "write_rate_limit": 10000},
        "production_ingest_limits_unchanged": {"per_bot_per_minute": 60, "global_per_minute": 1000},
        "limitations": [
            "Client HTTP+SDK timings, not server-only latency",
            "Synthetic loopback traffic",
            "No UI/live SLO or 100 concurrent client acceptance",
            "No payment actions during load",
            "30-minute L2, burst, backup and resource monitoring remain PM-022/021",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-file", type=Path)
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--bots", type=int, default=100)
    parser.add_argument("--readers", type=int, default=10)
    parser.add_argument("--rate", type=int, default=1000)
    parser.add_argument("--report", type=Path, default=Path(".local/backend-load.json"))
    args = parser.parse_args()
    if not (
        60 <= args.seconds <= 1800
        and 20 <= args.bots <= 100
        and 0 <= args.readers <= 100
        and 100 <= args.rate <= 1000
    ):
        parser.error("Use seconds 60..1800, bots 20..100, readers 0..100, rate 100..1000.")
    lab = Lab(args.connection_file)
    try:
        lab.open()
        result = measure(lab, args.seconds, args.bots, args.readers, args.rate)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result), flush=True)
        if result["result"] != "PASS":
            raise SystemExit(1)
    finally:
        lab.close()


if __name__ == "__main__":
    main()
