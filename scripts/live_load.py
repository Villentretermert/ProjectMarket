"""L1 live SLO: ten real browser sessions, ten bot identities, 100 messages/minute."""

import argparse
import json
import os
import platform
import secrets
import subprocess
from pathlib import Path
from uuid import uuid4

from scripts.backend_lab import Lab
from scripts.smoke_ingestion import Http


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-file", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".local/live-load"))
    parser.add_argument("--seconds", type=int, default=900)
    args = parser.parse_args()
    lab = Lab(args.connection_file)
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        lab.open()
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
        for index in range(10):
            kind = "news" if index < 4 else "product" if index < 8 else "chart"
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
            "output": str(args.output.resolve()),
        }
        result = subprocess.run(
            ["node", "apps/client/live-load.mjs"],
            input=json.dumps(config),
            text=True,
            env=dict(os.environ),
            check=False,
            timeout=args.seconds + 180,
        )
        if result.returncode:
            raise SystemExit(result.returncode)
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
        report["receipts"] = lab.query("SELECT count(*) AS n FROM message_receipts")[0]["n"]
        report["outbox"] = lab.query("SELECT count(*) AS n FROM change_outbox")[0]["n"]
        report["schema_bytes"] = lab.query(
            "SELECT coalesce(sum(pg_total_relation_size(c.oid)),0)::bigint AS n "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=%s AND c.relkind='r'",
            (lab.schema,),
        )[0]["n"]
        assert report["receipts"] == report["accepted"] + 10
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print("PASS: live load report and durable receipt count saved; disposable state removed.")
    finally:
        lab.close()


if __name__ == "__main__":
    main()
