"""Real HTTP burst and replay across API/DB restart. State is synthetic and secret."""

import argparse
import json
import math
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4


class Http:
    def __init__(self, origin: str):
        self.origin = origin.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        self.csrf = ""

    def call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        expected: int = 200,
        key: str = "",
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Origin": self.origin,
            "Content-Type": "application/json",
            "X-CSRF-Token": self.csrf,
        }
        if key:
            headers["Authorization"] = "Bearer " + key
        headers.update(extra_headers or {})
        request = Request(
            self.origin + path,
            method=method,
            headers=headers,
            data=json.dumps(body).encode() if body is not None else None,
        )
        try:
            response = self.opener.open(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            if response.status != expected:
                raise RuntimeError(f"HTTP check failed: {method} {path}: {response.status}")
            raw = response.read()
        return json.loads(raw) if raw else {}


def prepare(origin: str, state_path: Path, report_path: Path) -> None:
    if state_path.exists():
        raise SystemExit("State file already exists; finish the after phase first.")
    owner = Http(origin)
    credentials = {"username": "ingest_" + uuid4().hex[:20], "password": secrets.token_urlsafe(24)}
    owner.csrf = owner.call(
        "POST",
        "/v1/auth/register",
        {**credentials, "display_name": "Synthetic HTTP test"},
        expected=201,
    )["csrf_token"]
    try:
        owner.call("PUT", "/v1/account/business-profile", {"name": "Synthetic HTTP workspace"})
        bots = []
        for _ in range(4):
            registration = owner.call(
                "POST", "/v1/bots", {"name": "Synthetic ingress bot"}, expected=201
            )
            issued = owner.call(
                "POST",
                "/v1/bot-registrations/exchange",
                {},
                expected=201,
                key=registration["registration_credential"],
            )
            source = owner.call(
                "POST",
                "/v1/channels",
                {
                    "bot_id": issued["bot_id"],
                    "slug": "smoke-" + uuid4().hex,
                    "title": "Synthetic news",
                    "visibility": "selected",
                },
                expected=201,
            )
            bots.append(
                {
                    "key": issued["api_key"],
                    "bot_id": issued["bot_id"],
                    "channel_id": source["channel_id"],
                }
            )

        def send_batch(bot: dict[str, str]) -> dict[str, Any]:
            http = Http(origin)
            latencies = []
            sample: dict[str, Any] = {}
            for index in range(25):
                body = {
                    "schema_version": "1.0",
                    "message_id": "msg_" + uuid4().hex,
                    "channel_id": bot["channel_id"],
                    "resource_id": "news_item",
                    "source_revision": index + 1,
                    "occurred_at": "2026-10-22T00:00:00Z",
                    "kind": "text",
                    "payload": {"title": "Synthetic headline", "body": "x" * 512},
                }
                start = time.perf_counter()
                receipt = http.call("POST", "/v1/bot/messages", body, key=bot["key"])
                latencies.append((time.perf_counter() - start) * 1000)
                if not sample:
                    sample = {"body": body, "receipt": receipt, "key": bot["key"]}
            return {"latencies": latencies, "sample": sample}

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as executor:
            batches = list(executor.map(send_batch, bots))
        elapsed = time.perf_counter() - start
        latencies = sorted(value for batch in batches for value in batch["latencies"])
        state = {
            "credentials": credentials,
            "sample": batches[0]["sample"],
            "bot_id": bots[0]["bot_id"],
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        # The file intentionally contains ephemeral credentials. Never upload or print it.
        with os.fdopen(
            os.open(state_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
        ) as file:
            json.dump(state, file)
        report = {
            "transport": "real loopback HTTP",
            "bots": 4,
            "concurrent_clients": 4,
            "accepted": len(latencies),
            "payload_body_characters": 512,
            "elapsed_seconds": round(elapsed, 3),
            "requests_per_second": round(len(latencies) / elapsed, 2),
            "p50_ms": round(latencies[math.ceil(len(latencies) * 0.5) - 1], 2),
            "p95_ms": round(latencies[math.ceil(len(latencies) * 0.95) - 1], 2),
            "max_ms": round(max(latencies), 2),
            "errors": 0,
            "limitation": "Short synthetic burst, not sustained pilot capacity or UI latency.",
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))
    except BaseException:
        owner.call("DELETE", "/v1/account", {"password": credentials["password"]}, expected=204)
        raise


def replay(origin: str, state_path: Path) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    owner, bot = Http(origin), Http(origin)
    try:
        sample = state["sample"]
        result = bot.call("POST", "/v1/bot/messages", sample["body"], key=sample["key"])
        if result != sample["receipt"]:
            raise RuntimeError("Restart replay did not preserve the original receipt")
        changed = {**sample["body"], "payload": {"title": "Changed", "body": "Conflict"}}
        bot.call("POST", "/v1/bot/messages", changed, expected=409, key=sample["key"])
        owner.csrf = owner.call("POST", "/v1/auth/login", state["credentials"])["csrf_token"]
        owner.call("DELETE", "/v1/bots/" + state["bot_id"], expected=204)
        bot.call("POST", "/v1/bot/messages", sample["body"], expected=401, key=sample["key"])
        print("HTTP ingestion restart replay, conflict and revoked-key replay checks passed")
    finally:
        owner.csrf = owner.call("POST", "/v1/auth/login", state["credentials"])["csrf_token"]
        owner.call(
            "DELETE", "/v1/account", {"password": state["credentials"]["password"]}, expected=204
        )
        state_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    parser.add_argument("--state", type=Path, default=Path(".local/ingest-smoke.json"))
    parser.add_argument("--report", type=Path, default=Path(".local/ingestion-burst.json"))
    args = parser.parse_args()
    if args.phase == "before":
        prepare(args.url, args.state, args.report)
    else:
        replay(args.url, args.state)


if __name__ == "__main__":
    main()
