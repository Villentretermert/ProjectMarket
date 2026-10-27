"""Two independent bot processes/containers, same public API, isolated synthetic owner."""

import argparse
import json
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from marketob_sdk import APIError, BotClient

from scripts.pilot_bots import COMPOSE, bot_environment, provision, publish, run_bot
from scripts.smoke_ingestion import Http


def smoke(origin: str, mode: str, report: Path) -> None:
    BotClient(origin)
    owner = Http(origin)
    credentials = {"username": "bots_" + uuid4().hex[:16], "password": secrets.token_urlsafe(24)}
    owner.csrf = owner.call(
        "POST",
        "/v1/auth/register",
        {**credentials, "display_name": "Synthetic bot test"},
        expected=201,
    )["csrf_token"]
    directory = Path(".local") / ("bot-smoke-" + uuid4().hex)
    volumes = "marketob-test-" + uuid4().hex
    try:
        channels = provision(owner, directory)
        env = bot_environment(directory, volumes)
        if mode == "docker":
            subprocess.run(COMPOSE + ["build", "catalog-bot", "news-bot"], env=env, check=True)
            check = (
                "import os, importlib.util, subprocess; assert os.getuid() == 10001; "
                "assert subprocess.check_output(['dpkg-query','-W','-f=${Version}\\n',"
                "'libssl3','openssl'], text=True).splitlines() == ['3.0.22-1~deb12u2'] * 2; "
                "assert not os.environ.get('MARKETOB_DATABASE_URL'); "
                "assert not os.environ.get('POSTGRES_PASSWORD'); "
                "assert importlib.util.find_spec('marketob_api') is None; "
                "assert importlib.util.find_spec('psycopg') is None; "
                "assert importlib.util.find_spec('pytest') is None; "
                "assert importlib.util.find_spec('contracts.reference_model') is None"
            )
            subprocess.run(
                COMPOSE + ["run", "--rm", "--no-deps", "catalog-bot", "python", "-c", check],
                env=env,
                check=True,
            )
        for kind in channels:
            run_bot(kind, directory, mode, True, volumes)
        publish(owner, channels)
        snapshots = {
            kind: owner.call("GET", "/v1/channels/" + channel["slug"])
            for kind, channel in channels.items()
        }
        assert len(snapshots["catalog"]["records"]) == 4
        assert len(snapshots["news"]["records"]) == 6
        for channel in channels.values():
            Http(origin).call("GET", "/v1/channels/" + channel["slug"], expected=404)
        news_values = dict(
            line.split("=", 1)
            for line in (directory / "news.env").read_text(encoding="utf-8").splitlines()
        )
        news = BotClient(origin, news_values["MARKETOB_BOT_KEY"])
        try:
            news.send_message(
                {
                    "schema_version": "1.0",
                    "message_id": "wrong_channel",
                    "channel_id": channels["catalog"]["channel_id"],
                    "resource_id": "wrong_channel",
                    "source_revision": 1,
                    "occurred_at": datetime.now(UTC).isoformat(),
                    "kind": "data",
                    "content_type": "news",
                    "payload": {"title": "Synthetic", "body": "Test"},
                }
            )
        except APIError as error:
            assert error.status == 404
        else:
            raise AssertionError("A bot wrote another bot channel")
        requests = [
            owner.call(
                "POST",
                "/v1/channels/" + channels["catalog"]["channel_id"] + "/actions",
                {
                    "action_id": "request_" + resource,
                    "resource_id": resource,
                    "observed_source_revision": 1,
                    "quantity": 1,
                },
                expected=202,
                extra_headers={"Idempotency-Key": "demo_" + resource},
            )
            for resource in ("soap", "paper_towels")
        ]
        run_bot("catalog", directory, mode, True, volumes)
        for request, state in zip(requests, ("confirmed", "failed"), strict=True):
            assert (
                owner.call("GET", "/v1/action-requests/" + request["action_request_id"])["state"]
                == state
            )
        for kind in channels:
            run_bot(kind, directory, mode, True, volumes)
            assert owner.call("GET", "/v1/channels/" + channels[kind]["slug"]) == snapshots[kind]
        report.parent.mkdir(parents=True, exist_ok=True)
        result = {
            "result": "PASS",
            "mode": mode,
            "catalog_records": 4,
            "news_chart_records": 6,
            "outcomes": ["confirmed", "failed"],
            "restart_unchanged_data": True,
            "cross_bot_write_rejected": True,
            "private_anonymous_rejected": True,
        }
        report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))
    finally:
        owner.retire_test_workspace()
        # Only these randomly named disposable volumes belong to this invocation.
        if mode == "docker":
            assert volumes.startswith("marketob-test-") and len(volumes) == 46
            subprocess.run(
                ["docker", "volume", "rm", volumes + "-catalog", volumes + "-news"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        # Remove the two credentials, retain non-secret state/evidence for diagnosis.
        for kind in ("catalog", "news"):
            (directory / (kind + ".env")).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", choices=("python", "docker"), default="python")
    parser.add_argument("--report", type=Path, default=Path(".local/bot-smoke-report.json"))
    args = parser.parse_args()
    smoke(args.url, args.mode, args.report)


if __name__ == "__main__":
    main()
