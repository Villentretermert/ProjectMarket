"""Exercise real HTTP identity without printing passwords, cookies or CSRF values."""

import argparse
import json
import secrets
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--bots", action="store_true", help="Also exercise bot registration/revocation"
    )
    args = parser.parse_args()
    origin = args.url.rstrip("/")
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    csrf = ""

    def call(
        method: str, path: str, body: dict[str, Any] | None, expected: int, bearer: str = ""
    ) -> dict[str, Any]:
        request = Request(
            origin + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                "Origin": origin,
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf,
                **({"Authorization": "Bearer " + bearer} if bearer else {}),
            },
        )
        try:
            response = opener.open(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            if response.status != expected:
                raise SystemExit(f"Identity smoke failed: {method} {path}, HTTP {response.status}")
            raw = response.read()
        return json.loads(raw) if raw else {}

    username = "smoke_" + uuid4().hex[:20]
    credentials = {"username": username, "password": secrets.token_urlsafe(24)}
    registered = call(
        "POST", "/v1/auth/register", {**credentials, "display_name": "HTTP smoke"}, 201
    )
    csrf = registered["csrf_token"]
    try:
        call("GET", "/v1/auth/session", None, 200)
        call("PUT", "/v1/account/business-profile", {"name": "Smoke workspace"}, 200)
        if args.bots:
            registration = call("POST", "/v1/bots", {"name": "Smoke bot"}, 201)
            token = registration["registration_credential"]
            issued = call("POST", "/v1/bot-registrations/exchange", {}, 201, token)
            call("POST", "/v1/bot-registrations/exchange", {}, 401, token)
            identity = call("GET", "/v1/bot/identity", None, 200, issued["api_key"])
            assert identity["bot_id"] == issued["bot_id"]
            inventory = call("GET", "/v1/bots/" + issued["bot_id"] + "/keys", None, 200)
            assert issued["api_key"] not in json.dumps(inventory)
            call("DELETE", "/v1/bots/" + issued["bot_id"], None, 204)
            call("GET", "/v1/bot/identity", None, 401, issued["api_key"])
            print(
                "HTTP bot smoke passed: create, exchange, replay denied, "
                "identity, inventory, revoke"
            )
        valid_csrf = csrf
        csrf = "invalid"
        call("DELETE", "/v1/auth/session", None, 403)
        csrf = valid_csrf
        call("DELETE", "/v1/auth/session", None, 204)
        call("GET", "/v1/auth/session", None, 401)
    finally:
        logged_in = call("POST", "/v1/auth/login", credentials, 200)
        csrf = logged_in["csrf_token"]
        call(
            "DELETE",
            "/v1/account",
            {"password": credentials["password"], "confirmation": "DELETE"},
            409,
        )
        call("DELETE", "/v1/auth/session", None, 204)
    print(
        "HTTP identity smoke passed: register, session, business profile, "
        "CSRF, logout, ownership deletion guard"
    )


if __name__ == "__main__":
    main()
