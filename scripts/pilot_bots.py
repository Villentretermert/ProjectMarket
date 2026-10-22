"""Provision a private local pilot through owner HTTP API; never print credentials."""

import argparse
import getpass
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from marketob_bots.catalog import PRODUCTS
from marketob_bots.common import ENV_KEYS, RSS_URL
from marketob_sdk import BotClient

from scripts.smoke_ingestion import Http

COMPOSE = [
    "docker",
    "compose",
    "-f",
    "compose.yaml",
    "-f",
    "compose.bots.yaml",
    "--profile",
    "demo-bots",
]


def private_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8"
    ) as stream:
        stream.write(text)


def provision(owner: Http, directory: Path) -> dict[str, Any]:
    if directory.exists():
        raise RuntimeError("Choose a new state directory; existing bot state must be preserved.")
    directory.mkdir(parents=True)
    owner.call("PUT", "/v1/account/business-profile", {"name": "MarkeTOB Pilot"})
    result: dict[str, Any] = {}
    for kind, title in [("catalog", "Everyday goods · demo"), ("news", "Public feed")]:
        registration = owner.call("POST", "/v1/bots", {"name": title}, expected=201)
        issued = BotClient(owner.origin).exchange_registration(
            registration["registration_credential"]
        )
        channel = owner.call(
            "POST",
            "/v1/channels",
            {
                "bot_id": issued["bot_id"],
                "title": title,
                "slug": kind + "-" + uuid4().hex[:16],
            },
            expected=201,
        )
        values = {
            "MARKETOB_API_URL": owner.origin,
            "MARKETOB_BOT_KEY": issued["api_key"],
            "MARKETOB_CHANNEL_ID": channel["channel_id"],
            "MARKETOB_STATE_PATH": str((directory / (kind + ".sqlite3")).resolve()),
            "MARKETOB_RSS_URL": RSS_URL,
        }
        private_write(
            directory / (kind + ".env"), "\n".join(k + "=" + v for k, v in values.items()) + "\n"
        )
        result[kind] = channel
        # Preserve completed provisioning if a later call fails; do not recreate keys blindly.
        (directory / "channels.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def bot_environment(directory: Path, volumes: str | None = None) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ENV_KEYS | {"MARKETOB_DATABASE_URL", "POSTGRES_PASSWORD"}
    }
    for kind in ("catalog", "news"):
        env["MARKETOB_" + kind.upper() + "_ENV_FILE"] = str((directory / (kind + ".env")).resolve())
        if volumes:
            env["MARKETOB_" + kind.upper() + "_STATE_VOLUME"] = volumes + "-" + kind
    return env


def run_bot(
    kind: str, directory: Path, mode: str, offline: bool, volumes: str | None = None
) -> None:
    if mode == "docker":
        command = COMPOSE + [
            "run",
            "--rm",
            "--no-deps",
            kind + "-bot",
            "python",
            "-m",
            "marketob_bots." + kind,
            "--once",
        ]
    else:
        command = [
            sys.executable,
            "-m",
            "marketob_bots." + kind,
            "--env-file",
            str(directory / (kind + ".env")),
            "--once",
        ]
    if kind == "news" and offline:
        command.append("--offline")
    subprocess.run(
        command,
        env=bot_environment(directory, volumes),
        check=True,
        timeout=180,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )


def publish(owner: Http, channels: dict[str, Any]) -> None:
    for kind, channel in channels.items():
        route = "/v1/owner/channels/" + channel["channel_id"]
        current = owner.call("GET", route)
        version = current["layout"]["template_version"]
        resources = (
            list(PRODUCTS)
            if kind == "catalog"
            else [f"news_{n}" for n in range(1, 6)] + ["feed_activity"]
        )
        blocks, actions = [], []
        for resource in resources:
            content = (
                "product"
                if kind == "catalog"
                else ("chart" if resource == "feed_activity" else "news")
            )
            block: dict[str, Any] = {
                "block_id": resource,
                "source": {"channel_id": channel["channel_id"], "resource_id": resource},
                "content_type": content,
                "view": {"chart": "line", "news": "compact", "product": "card"}[content],
                "action_ids": [],
            }
            if content == "product":
                block["action_ids"] = ["request_" + resource]
                actions.append(
                    {
                        "action_id": "request_" + resource,
                        "resource_id": resource,
                        "kind": "request_purchase",
                        "label": "Request purchase",
                    }
                )
            blocks.append(block)
        owner.call(
            "PUT",
            route,
            {
                "title": current["title"],
                "visibility": "selected",
                "expected_template_version": version,
                "layout": {**current["layout"], "template_version": version + 1, "blocks": blocks},
                "actions": actions,
            },
        )
        owner.call("POST", route + "/publish", {"expected_template_version": version + 1})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--create-account", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--directory", type=Path, default=Path(".local/pilot"))
    parser.add_argument("--mode", choices=("python", "docker"), default="python")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    BotClient(args.url)  # Validate TLS/origin before sending any owner credentials.
    owner = Http(args.url)
    credentials = {
        "username": args.username,
        "password": getpass.getpass("Local account password: "),
    }
    owner.csrf = owner.call(
        "POST",
        "/v1/auth/" + ("register" if args.create_account else "login"),
        {**credentials, **({"display_name": "Pilot owner"} if args.create_account else {})},
        expected=201 if args.create_account else 200,
    )["csrf_token"]
    channels = (
        json.loads((args.directory / "channels.json").read_text(encoding="utf-8"))
        if args.resume
        else provision(owner, args.directory)
    )
    if set(channels) != {"catalog", "news"}:
        raise RuntimeError(
            "Provisioning was incomplete. Inspect owner bot/channel lists before retrying."
        )
    if args.mode == "docker":
        subprocess.run(
            COMPOSE + ["build", "catalog-bot", "news-bot"],
            env=bot_environment(args.directory),
            check=True,
        )
    for kind in channels:
        run_bot(kind, args.directory, args.mode, args.offline)
    publish(owner, channels)
    print("Private pilot ready. Start each bot continuously using its own saved configuration.")
    for kind, channel in channels.items():
        print(kind + ": " + args.url + "/v1/channels/" + channel["slug"])


if __name__ == "__main__":
    main()
