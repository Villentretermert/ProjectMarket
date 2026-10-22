"""Exercise publication over real HTTP on a disposable local instance; no secrets in output."""

import argparse
import secrets
from typing import Any
from uuid import uuid4

from scripts.smoke_ingestion import Http


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    owner, bot, anonymous = (Http(args.url) for _ in range(3))
    suffix = uuid4().hex[:16]
    password = secrets.token_urlsafe(24)
    owner.csrf = owner.call(
        "POST",
        "/v1/auth/register",
        {
            "username": "channel_" + suffix,
            "password": password,
            "display_name": "Synthetic channels",
        },
        expected=201,
    )["csrf_token"]
    try:
        owner.call("PUT", "/v1/account/business-profile", {"name": "Channel checks"})
        registered = owner.call("POST", "/v1/bots", {"name": "Channel check bot"}, expected=201)
        issued = bot.call(
            "POST",
            "/v1/bot-registrations/exchange",
            {},
            expected=201,
            key=registered["registration_credential"],
        )
        source = owner.call(
            "POST",
            "/v1/channels",
            {"bot_id": issued["bot_id"], "slug": "check-" + suffix, "title": "Synthetic news"},
            expected=201,
        )
        assert source["visibility"] == "selected"
        management = "/v1/owner/channels/" + source["channel_id"]
        public = "/v1/channels/" + source["slug"]
        bot.call(
            "POST",
            "/v1/bot/messages",
            {
                "schema_version": "1.0",
                "message_id": "first",
                "channel_id": source["channel_id"],
                "resource_id": "news",
                "source_revision": 1,
                "occurred_at": "2026-10-22T00:00:00Z",
                "kind": "text",
                "payload": {"title": "First item", "body": "Synthetic HTTP check"},
            },
            key=issued["api_key"],
        )
        body: dict[str, Any] = {
            "title": "Published title",
            "visibility": "public",
            "expected_template_version": 1,
            "layout": {
                **source["layout"],
                "template_version": 2,
                "blocks": [
                    {
                        "block_id": "news",
                        "source": {"channel_id": source["channel_id"], "resource_id": "news"},
                        "content_type": "news",
                        "view": "compact",
                        "action_ids": [],
                    }
                ],
            },
            "actions": [],
        }
        owner.call("PUT", management, body)
        anonymous.call("GET", public, expected=404)
        owner.call("POST", management + "/publish", {"expected_template_version": 2})
        snapshot = anonymous.call("GET", public)
        assert snapshot["records"][0]["content"]["title"] == "First item"
        body["title"] = "Private draft"
        body["visibility"] = "selected"
        body["expected_template_version"] = 2
        body["layout"]["template_version"] = 3
        owner.call("PUT", management, body)
        assert anonymous.call("GET", public) == snapshot
        owner.call("POST", management + "/publish", {"expected_template_version": 3})
        anonymous.call("GET", public, expected=404)
        owner.call(
            "POST",
            management + "/rollback",
            {"expected_template_version": 3, "target_template_version": 2},
        )
        restored = anonymous.call("GET", public)
        assert restored["channel"]["layout"]["template_version"] == 4
        assert restored["channel"]["title"] == "Published title"
        owner.call("DELETE", management, expected=204)
        anonymous.call("GET", public, expected=404)
        print(
            "HTTP channels PASS: selected default, draft isolation, publish, "
            "private access, rollback, delete"
        )
    finally:
        owner.call("DELETE", "/v1/account", {"password": password}, expected=204)


if __name__ == "__main__":
    main()
