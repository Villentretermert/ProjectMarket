"""L1/L2 live SLO using real browser sessions and isolated bot identities."""

import argparse
import json
import os
import platform
import secrets
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from scripts.backend_lab import Lab
from scripts.host_samples import HostSamples
from scripts.load_integrity import receipt_manifest
from scripts.operations import log_metrics, snapshot
from scripts.smoke_ingestion import Http


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-file", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".local/live-load"))
    parser.add_argument("--seconds", type=int, default=900)
    parser.add_argument("--bots", type=int, choices=(10, 100), default=10)
    parser.add_argument("--burst", action="store_true")
    args = parser.parse_args()
    lab = Lab(args.connection_file)
    resources = HostSamples()
    resources.start()
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        lab.open()
        lab.start("worker")
        owner = Http(lab.origin)
        password = secrets.token_urlsafe(24)
        owner.csrf = owner.call(
            "POST",
            "/v1/auth/register",
            {
                "username": "load_" + uuid4().hex[:12],
                "password": password,
                "display_name": "Synthetic load owner",
            },
            expected=201,
        )["csrf_token"]
        owner.call("PUT", "/v1/account/business-profile", {"name": "L1 synthetic workspace"})
        sources = []
        for index in range(args.bots):
            kind = "news" if index % 10 < 4 else "product" if index % 10 < 8 else "chart"
            registration = owner.call("POST", "/v1/bots", {"name": f"L1 bot {index}"}, expected=201)
            issued = owner.call(
                "POST",
                "/v1/bot-registrations/exchange",
                {},
                key=registration["registration_credential"],
                expected=201,
            )
            source = owner.call(
                "POST",
                "/v1/channels",
                {
                    "bot_id": issued["bot_id"],
                    "slug": f"l1-{index}-" + uuid4().hex[:8],
                    "title": f"Live {kind} {index}",
                },
                expected=201,
            )
            source.update(key=issued["api_key"], kind=kind, index=index)
            title = f"L1 {index} revision 1"
            payload: dict[str, Any]
            if kind == "news":
                payload = {"title": title, "body": "Synthetic news. " * 210}
            elif kind == "product":
                payload = {
                    "title": title,
                    "description": "Synthetic product. " * 180,
                    "price": {"amount_minor": 200, "currency": "EUR"},
                    "availability": "in_stock",
                }
            else:
                payload = {
                    "title": title,
                    "x_label": "Sample",
                    "x_kind": "number",
                    "y_label": "Value",
                    "unit": "units",
                    "series": [
                        {
                            "name": "Main",
                            "points": [{"x": n, "y": (n * 17) % 83} for n in range(800)],
                        }
                    ],
                }
            source["message"] = {
                "schema_version": "1.0",
                "message_id": "seed",
                "channel_id": source["channel_id"],
                "resource_id": "sample",
                "source_revision": 1,
                "occurred_at": "2026-10-23T00:00:00Z",
                "kind": "data",
                "content_type": kind,
                "payload": payload,
            }
            owner.call("POST", "/v1/bot/messages", source["message"], key=source["key"])
            route = "/v1/owner/channels/" + source["channel_id"]
            current = owner.call("GET", route)
            version = current["layout"]["template_version"]
            actions = (
                [
                    {
                        "action_id": "purchase",
                        "resource_id": "sample",
                        "kind": "request_purchase",
                        "label": "Request purchase",
                    }
                ]
                if kind == "product"
                else []
            )
            block = {
                "block_id": "sample",
                "source": {"channel_id": source["channel_id"], "resource_id": "sample"},
                "content_type": kind,
                "view": {"news": "article", "product": "list", "chart": "line"}[kind],
                "action_ids": [a["action_id"] for a in actions],
            }
            owner.call(
                "PUT",
                route,
                {
                    "title": current["title"],
                    "visibility": "selected",
                    "expected_template_version": version,
                    "layout": {
                        **current["layout"],
                        "template_version": version + 1,
                        "blocks": [block],
                    },
                    "actions": actions,
                },
            )
            owner.call("POST", route + "/publish", {"expected_template_version": version + 1})
            reader = Http(lab.origin)
            username = "reader_" + uuid4().hex[:12]
            account = reader.call(
                "POST",
                "/v1/auth/register",
                {"username": username, "password": password, "display_name": f"L1 reader {index}"},
                expected=201,
            )
            owner.call("PUT", route + "/grants/" + account["user"]["user_id"], {}, expected=204)
            source["credentials"] = {"username": username, "password": password}
            sources.append(source)
        config = {
            "origin": lab.origin,
            "sources": sources,
            "seconds": args.seconds,
            "rate": args.bots * 10,
            "burst": args.burst,
            "output": str(args.output.resolve()),
        }
        process = subprocess.Popen(
            ["node", "apps/client/live-load.mjs"],
            stdin=subprocess.PIPE,
            text=True,
            env=dict(os.environ),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        # Track the browser's process tree so timeout/failure cannot leave 100 contexts running.
        lab.processes["browser"] = process  # type: ignore[assignment]
        process.communicate(json.dumps(config), timeout=args.seconds + 900)
        report_path = args.output / "live-load.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["runtime"] = {
            "python": platform.python_version(),
            "os": platform.platform(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "network": "127.0.0.1 loopback",
        }
        report["database"] = lab.query("SELECT version() AS version")[0]["version"]
        report["host_samples"] = resources.finish()
        report["receipts"] = lab.query("SELECT count(*) AS n FROM message_receipts")[0]["n"]
        report["outbox"] = lab.query("SELECT count(*) AS n FROM change_outbox")[0]["n"]
        report["schema_bytes"] = lab.query(
            "SELECT coalesce(sum(pg_total_relation_size(c.oid)),0)::bigint AS n "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=%s AND c.relkind='r'",
            (lab.schema,),
        )[0]["n"]
        report["operations"] = snapshot(lab.database)
        report["server"] = log_metrics(
            lab.directory / "logs", report["steady_started_at"], report["steady_finished_at"]
        )
        expected_steady = int(args.seconds * config["rate"] / 60)
        expected_burst = args.bots * 30 if args.burst else 0
        with lab.database.transaction() as connection:
            report["receipt_ids_before_restart"] = receipt_manifest(
                connection, args.bots, expected_steady, expected_burst
            )
        # Persist diagnostics before assertions: ambiguous HTTP outcomes must remain inspectable.
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        lab.stop("worker")
        lab.stop("api")
        lab.start("api")
        lab.start("worker")
        report["restart_receipts"] = lab.query("SELECT count(*) AS n FROM message_receipts")[0]["n"]
        with lab.database.transaction() as connection:
            report["receipt_ids_after_restart"] = receipt_manifest(
                connection, args.bots, expected_steady, expected_burst
            )
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if process.returncode:
            raise SystemExit(process.returncode)
        assert report["receipts"] == report["accepted"] + args.bots
        assert report["restart_receipts"] == report["receipts"]
        assert report["receipt_ids_after_restart"] == {
            "expected": args.bots + expected_steady + expected_burst,
            "actual": report["receipts"],
            "missing": 0,
            "unexpected": 0,
        }
        assert report["server"]["window_complete"]
        assert (report["server"]["unexpected_5xx_fraction"] or 0) < 0.01
        for route in ("POST /v1/bot/messages", "GET /v1/channels/{slug}"):
            metric = report["server"]["routes"][route]
            assert metric["p95_ms"] <= 500 and metric["p99_ms"] <= 2000, route
        print("PASS: live load and restart evidence saved; disposable state removed.")
    finally:
        resources.finish()
        lab.close()


if __name__ == "__main__":
    main()
