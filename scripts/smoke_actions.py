"""Durable HTTP actions across process/database restart; synthetic credentials stay local."""

import argparse
import json
import os
import secrets
from pathlib import Path
from typing import Any
from uuid import uuid4

from scripts.smoke_ingestion import Http


def prepare(origin: str, path: Path) -> None:
    if path.exists():
        raise RuntimeError("Finish the existing after phase before creating another run.")
    owner, bot = Http(origin), Http(origin)
    suffix = uuid4().hex[:16]
    credentials = {"username": "actions_" + suffix, "password": secrets.token_urlsafe(24)}
    owner.csrf = owner.call(
        "POST",
        "/v1/auth/register",
        {**credentials, "display_name": "Synthetic actions"},
        expected=201,
    )["csrf_token"]
    try:
        owner.call("PUT", "/v1/account/business-profile", {"name": "Action checks"})
        registered = owner.call("POST", "/v1/bots", {"name": "Synthetic catalog"}, expected=201)
        issued = bot.call(
            "POST",
            "/v1/bot-registrations/exchange",
            {},
            key=registered["registration_credential"],
            expected=201,
        )
        key = issued["api_key"]
        source = owner.call(
            "POST",
            "/v1/channels",
            {"bot_id": issued["bot_id"], "slug": "actions-" + suffix, "title": "Synthetic catalog"},
            expected=201,
        )
        bot.call(
            "POST",
            "/v1/bot/messages",
            {
                "schema_version": "1.0",
                "message_id": "soap",
                "channel_id": source["channel_id"],
                "resource_id": "soap",
                "source_revision": 1,
                "occurred_at": "2026-10-22T00:00:00Z",
                "kind": "data",
                "content_type": "product",
                "payload": {
                    "title": "Soap",
                    "description": "Synthetic daily item",
                    "price": {"amount_minor": 200, "currency": "EUR"},
                    "availability": "in_stock",
                },
            },
            key=key,
        )
        management = "/v1/owner/channels/" + source["channel_id"]
        owner.call(
            "PUT",
            management,
            {
                "title": source["title"],
                "visibility": "selected",
                "expected_template_version": 1,
                "layout": {
                    **source["layout"],
                    "template_version": 2,
                    "blocks": [
                        {
                            "block_id": "soap",
                            "source": {"channel_id": source["channel_id"], "resource_id": "soap"},
                            "content_type": "product",
                            "view": "card",
                            "action_ids": ["request_soap"],
                        }
                    ],
                },
                "actions": [
                    {
                        "action_id": "request_soap",
                        "resource_id": "soap",
                        "kind": "request_purchase",
                        "label": "Request purchase",
                    }
                ],
            },
        )
        owner.call("POST", management + "/publish", {"expected_template_version": 2})
        body = {
            "action_id": "request_soap",
            "resource_id": "soap",
            "observed_source_revision": 1,
            "quantity": 1,
        }
        requests = [
            owner.call(
                "POST",
                "/v1/channels/" + source["channel_id"] + "/actions",
                body,
                expected=202,
                extra_headers={"Idempotency-Key": "purchase_" + str(n)},
            )
            for n in range(2)
        ]
        events = bot.call("GET", "/v1/bot/events", key=key)["items"]
        assert len(events) == 2
        ack = bot.call("POST", "/v1/bot/events/" + events[1]["event_id"] + "/ack", {}, key=key)
        state = {
            "credentials": credentials,
            "key": key,
            "source": source,
            "requests": requests,
            "events": events,
            "ack": ack,
            "body": body,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
            json.dump(state, file)
        print("HTTP actions before restart PASS: two requests, one pending and one ACKed")
    except BaseException:
        owner.call("DELETE", "/v1/account", {"password": credentials["password"]}, expected=204)
        raise


def recover(origin: str, path: Path) -> None:
    state: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    owner, bot = Http(origin), Http(origin)
    owner.csrf = owner.call("POST", "/v1/auth/login", state["credentials"])["csrf_token"]
    try:
        key, events = state["key"], state["events"]
        assert bot.call("GET", "/v1/bot/events", key=key)["items"] == [events[0]]
        assert bot.call("GET", "/v1/bot/requests", key=key)["items"] == events
        for index, event in enumerate(events):
            route = "/v1/bot/events/" + event["event_id"]
            ack = bot.call("POST", route + "/ack", {}, key=key)
            if index == 1:
                assert ack == state["ack"]
            result = {
                "result_id": "result_" + str(index),
                "result_revision": 1,
                "state": "confirmed" if index == 0 else "failed",
                "summary": "Synthetic result. No payment.",
            }
            final = bot.call("POST", route + "/result", result, key=key)
            assert bot.call("POST", route + "/result", result, key=key) == final
            assert owner.call("GET", "/v1/action-requests/" + event["action_request_id"]) == final
        assert bot.call("GET", "/v1/bot/requests", key=key)["items"] == []
        replay = owner.call(
            "POST",
            "/v1/channels/" + state["source"]["channel_id"] + "/actions",
            state["body"],
            expected=202,
            extra_headers={"Idempotency-Key": "purchase_0"},
        )
        assert replay["action_request_id"] == state["requests"][0]["action_request_id"]
        assert replay["state"] == "confirmed"
        print("HTTP actions restart PASS: pending/ACK recovery, confirmed/failed, dedup, status")
    finally:
        owner.call(
            "DELETE", "/v1/account", {"password": state["credentials"]["password"]}, expected=204
        )
        path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    parser.add_argument("--state", type=Path, default=Path(".local/action-smoke.json"))
    args = parser.parse_args()
    (prepare if args.phase == "before" else recover)(args.url, args.state)


if __name__ == "__main__":
    main()
