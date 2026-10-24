"""Verify the local HTTPS proxy using its exported CA, without modifying OS trust."""

import argparse
import json
import secrets
import ssl
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca", type=Path, required=True)
    args = parser.parse_args()
    origin = "https://localhost:8443"
    context = ssl.create_default_context(cafile=str(args.ca))
    jar = CookieJar()
    http = build_opener(HTTPSHandler(context=context), HTTPCookieProcessor(jar))
    csrf = ""

    def call(method: str, path: str, body: dict[str, str] | None = None) -> bytes:
        request = Request(
            origin + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Origin": origin, "Content-Type": "application/json", "X-CSRF-Token": csrf},
        )
        with http.open(request, timeout=10) as response:
            return bytes(response.read())

    assert json.loads(call("GET", "/health/ready"))["database"] == "ok"
    assert b"MarkeTOB" in call("GET", "/app/")
    password = secrets.token_urlsafe(24)
    account = json.loads(
        call(
            "POST",
            "/v1/auth/register",
            {
                "username": "tls_" + secrets.token_hex(12),
                "password": password,
                "display_name": "Disposable HTTPS verification",
            },
        )
    )
    csrf = account["csrf_token"]
    assert any(cookie.secure for cookie in jar), "TLS session must have a Secure cookie"
    assert json.loads(call("GET", "/v1/auth/session"))["user"] == account["user"]
    call("DELETE", "/v1/account", {"password": password, "confirmation": "DELETE"})
    print("HTTPS CA verification, Web, local login, Secure session and account deletion: PASS")


if __name__ == "__main__":
    main()
