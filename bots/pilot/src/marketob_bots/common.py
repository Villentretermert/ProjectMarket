"""Small CLI configuration shared by the two independent demo processes."""

import argparse
import json
import os
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from marketob_sdk import APIError, BotClient, ProtocolError, TransportError
from marketob_sdk.client import identifier

from marketob_bots.state import Journal, StateError

RSS_URL = "https://feeds.bbci.co.uk/news/world/rss.xml"
ENV_KEYS = {
    "MARKETOB_API_URL",
    "MARKETOB_BOT_KEY",
    "MARKETOB_CHANNEL_ID",
    "MARKETOB_STATE_PATH",
    "MARKETOB_RSS_URL",
    "MARKETOB_ALLOW_CONTAINER_HTTP",
}


class FeedError(Exception):
    """No valid new feed is available; keep the latest previously published data."""


@dataclass(frozen=True)
class Configuration:
    api_url: str
    channel_id: str
    state_path: Path
    key: str = field(repr=False)
    rss_url: str = RSS_URL
    allow_container_http: bool = False
    offline: bool = False


def configuration(kind: str, env_file: Path | None, offline: bool = False) -> Configuration:
    if os.environ.get("MARKETOB_DATABASE_URL") or os.environ.get("POSTGRES_PASSWORD"):
        raise StateError("Do not pass platform database credentials to a bot process.")
    values: dict[str, str] = {}
    if env_file:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            name, separator, value = line.partition("=")
            if not separator or name not in ENV_KEYS or name in values:
                raise StateError("Bot configuration must contain unique supported KEY=value lines.")
            values[name] = value.strip()
    values.update({key: os.environ[key] for key in ENV_KEYS if key in os.environ})
    for required in ("MARKETOB_BOT_KEY", "MARKETOB_CHANNEL_ID"):
        if not values.get(required):
            raise StateError(
                "Set " + required + " in a private bot configuration file or environment."
            )
    return Configuration(
        api_url=values.get("MARKETOB_API_URL", "http://127.0.0.1:8000"),
        channel_id=identifier(values["MARKETOB_CHANNEL_ID"]),
        state_path=Path(values.get("MARKETOB_STATE_PATH", ".local/" + kind + ".sqlite3")),
        key=values["MARKETOB_BOT_KEY"],
        rss_url=values.get("MARKETOB_RSS_URL", RSS_URL),
        allow_container_http=values.get("MARKETOB_ALLOW_CONTAINER_HTTP") == "1",
        offline=offline,
    )


def run(
    kind: str, cycle: Callable[[BotClient, Journal, Configuration], dict[str, int]], interval: float
) -> None:
    parser = argparse.ArgumentParser(description="MarkeTOB " + kind + " demo bot; no payments.")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=interval)
    parser.add_argument(
        "--offline", action="store_true", help="Use the bundled synthetic RSS fixture (news only)"
    )
    args = parser.parse_args()
    if not 1 <= args.interval <= 3600:
        parser.error("Interval must be 1..3600 seconds.")
    journal = None
    try:
        config = configuration(kind, args.env_file, args.offline)
        client = BotClient(
            config.api_url, config.key, allow_container_http=config.allow_container_http
        )
        journal = Journal(config.state_path, client.identity()["bot_id"], config.channel_id)
        while True:
            try:
                result = cycle(client, journal, config)
                print(
                    json.dumps(
                        {"bot": kind, "source": "synthetic" if config.offline else kind, **result}
                    ),
                    flush=True,
                )
            except (FeedError, TransportError) as error:
                print(str(error), flush=True)
                if args.once:
                    raise SystemExit(1) from None
            except APIError as error:
                print(str(error), flush=True)
                if args.once or error.status not in {429, 503}:
                    raise SystemExit(1) from None
                time.sleep(min(60, max(5, error.retry_after or 5)))
            if args.once:
                return
            time.sleep(args.interval)
    except (StateError, ProtocolError, APIError, TransportError) as error:
        print(str(error), flush=True)
        raise SystemExit(1) from None
    except OSError, sqlite3.Error:
        print("Bot configuration or local journal is unavailable.", flush=True)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        return
    finally:
        if journal is not None:
            journal.close()
