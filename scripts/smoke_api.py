"""Verify a running HTTP server; a 503 must be expected explicitly."""

import argparse
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def read(url: str) -> tuple[int, dict[str, Any]]:
    try:
        with urlopen(url, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        with error:
            return error.code, json.load(error)


def check(url: str, database: str, wait: float = 30) -> None:
    deadline = time.monotonic() + wait
    expected_code = 200 if database == "ok" else 503
    while True:
        try:
            live_code, live = read(url.rstrip("/") + "/health/live")
            ready_code, ready = read(url.rstrip("/") + "/health/ready")
            if (
                live_code == 200
                and live.get("service") == "marketob-api"
                and live.get("status") == "ok"
                and ready_code == expected_code
                and ready.get("database") == database
            ):
                for asset in (
                    "",
                    "app.js",
                    "api.js",
                    "dom.js",
                    "actions.js",
                    "render.js",
                    "styles.css",
                    "studio.js",
                    "studio-editor.js",
                    "favorites.js",
                    "space.js",
                    "sharing.js",
                    "live.js",
                ):
                    with urlopen(url.rstrip("/") + "/app/" + asset, timeout=5) as response:
                        assert response.status == 200
                        assert response.headers["Cache-Control"] == "no-store"
                        assert len(response.read()) > 100
                print(f"HTTP smoke passed: live=200, ready={ready_code}, database={database}")
                return
        except URLError, TimeoutError, ConnectionError:
            pass
        if time.monotonic() >= deadline:
            raise SystemExit(f"HTTP smoke failed: expected readiness database={database}")
        time.sleep(0.3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--database", choices=["ok", "not_configured", "unavailable"], required=True
    )
    args = parser.parse_args()
    check(args.url, args.database)


if __name__ == "__main__":
    main()
