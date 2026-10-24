"""Actual API/worker/bot termination and durable reconciliation in an isolated lab."""

import argparse
import json
import secrets
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from marketob_sdk import APIError, BotClient

from scripts.backend_lab import Lab
from scripts.pilot_bots import bot_environment, provision, publish, run_bot
from scripts.smoke_ingestion import Http


def faults(lab: Lab) -> dict[str, Any]:
    owner = Http(lab.origin)
    password = secrets.token_urlsafe(24)
    owner.csrf = owner.call(
        "POST",
        "/v1/auth/register",
        {
            "username": "fault_" + uuid4().hex[:16],
            "password": password,
            "display_name": "Synthetic fault owner",
        },
        expected=201,
    )["csrf_token"]
    directory = lab.directory / "bots"
    try:
        channels = provision(owner, directory)
        for kind in channels:
            run_bot(kind, directory, "python", True)
        publish(owner, channels)
        snapshots = {k: owner.call("GET", "/v1/channels/" + c["slug"]) for k, c in channels.items()}
        for c in channels.values():
            Http(lab.origin).call("GET", "/v1/channels/" + c["slug"], expected=404)
        phases = ["before_ack", "after_ack", "before_result", "after_result"]
        for phase in phases:
            request = owner.call(
                "POST",
                "/v1/channels/" + channels["catalog"]["channel_id"] + "/actions",
                {
                    "action_id": "request_soap",
                    "resource_id": "soap",
                    "observed_source_revision": 1,
                    "quantity": 1,
                },
                expected=202,
                extra_headers={"Idempotency-Key": "fault_" + phase},
            )
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.fault_bot",
                    "--env-file",
                    str(directory / "catalog.env"),
                    "--phase",
                    phase,
                ],
                env=bot_environment(directory),
                timeout=60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            assert process.returncode == 91
            lab.stop("api")
            lab.start("api")
            run_bot("catalog", directory, "python", True)
            status = owner.call("GET", "/v1/action-requests/" + request["action_request_id"])
            assert status["state"] == "confirmed"
            with sqlite3.connect(directory / "catalog.sqlite3") as journal:
                assert (
                    journal.execute(
                        "SELECT count(*) FROM demo_effects WHERE action_request_id=?",
                        (request["action_request_id"],),
                    ).fetchone()[0]
                    == 1
                )
                assert (
                    journal.execute(
                        "SELECT reported FROM inbox WHERE action_request_id=?",
                        (request["action_request_id"],),
                    ).fetchone()[0]
                    == 1
                )
            assert (
                lab.query(
                    "SELECT count(*) AS n FROM action_results WHERE action_request_id=%s",
                    (request["action_request_id"],),
                )[0]["n"]
                == 1
            )
            print("Crash boundary recovered: " + phase, flush=True)
        # Persisted ingestion/outbox can be reconciled without any running worker.
        values = dict(
            line.split("=", 1) for line in (directory / "news.env").read_text().splitlines()
        )
        news = BotClient(lab.origin, values["MARKETOB_BOT_KEY"], attempts=1)
        identity = news.identity()
        message = {
            "schema_version": "1.0",
            "message_id": "concurrent_duplicate",
            "channel_id": channels["news"]["channel_id"],
            "resource_id": "concurrent",
            "source_revision": 1,
            "occurred_at": datetime.now(UTC).isoformat(),
            "kind": "data",
            "content_type": "news",
            "payload": {"title": "Synthetic", "body": "Concurrent"},
        }
        with ThreadPoolExecutor(max_workers=8) as pool:
            receipts = list(pool.map(lambda _: news.send_message(message), range(8)))
        assert all(r == receipts[0] for r in receipts)
        assert (
            lab.query(
                "SELECT count(*) AS n FROM change_outbox WHERE receipt_id=%s",
                (receipts[0]["receipt_id"],),
            )[0]["n"]
            == 1
        )
        failed_message = {**message, "message_id": "atomic_failure", "resource_id": "atomic"}
        lab.query(
            "CREATE FUNCTION fail_test_outbox() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN IF NEW.receipt_id IS NOT NULL THEN RAISE EXCEPTION 'synthetic failure'; "
            "END IF; RETURN NEW; END $$"
        )
        lab.query(
            "CREATE TRIGGER test_outbox_failure BEFORE INSERT ON change_outbox "
            "FOR EACH ROW EXECUTE FUNCTION fail_test_outbox()"
        )
        try:
            try:
                news.send_message(failed_message)
            except APIError as error:
                assert error.status == 500 and error.code == "internal_error"
            else:
                raise AssertionError("Injected transaction failure was not reached")
            assert (
                lab.query(
                    "SELECT count(*) AS n FROM message_receipts WHERE message_id='atomic_failure'"
                )[0]["n"]
                == 0
            )
            assert (
                lab.query("SELECT count(*) AS n FROM source_records WHERE resource_id='atomic'")[0][
                    "n"
                ]
                == 0
            )
        finally:
            lab.query("DROP TRIGGER test_outbox_failure ON change_outbox")
            lab.query("DROP FUNCTION fail_test_outbox()")
        recovered = news.send_message(failed_message)
        assert (
            lab.query(
                "SELECT count(*) AS n FROM change_outbox WHERE receipt_id=%s",
                (recovered["receipt_id"],),
            )[0]["n"]
            == 1
        )
        lab.stop("api")
        lab.start("api")
        assert news.send_message(message) == receipts[0]
        # A restarted real maintenance process materializes a deliberately aged request.
        request = owner.call(
            "POST",
            "/v1/channels/" + channels["catalog"]["channel_id"] + "/actions",
            {
                "action_id": "request_soap",
                "resource_id": "soap",
                "observed_source_revision": 1,
                "quantity": 1,
            },
            expected=202,
            extra_headers={"Idempotency-Key": "worker_recovery"},
        )
        lab.start("worker")
        heartbeat = lab.directory / "marketob-maintenance-heartbeat"
        for _ in range(100):
            if heartbeat.exists():
                break
            time.sleep(0.1)
        assert heartbeat.exists()
        lab.stop("worker")
        lab.query(
            "UPDATE action_requests SET created_at=now()-interval '2 minutes' "
            "WHERE action_request_id=%s",
            (request["action_request_id"],),
        )
        assert (
            lab.query(
                "SELECT state FROM action_requests WHERE action_request_id=%s",
                (request["action_request_id"],),
            )[0]["state"]
            == "queued"
        )
        lab.start("worker")
        for _ in range(100):
            if (
                lab.query(
                    "SELECT state FROM action_requests WHERE action_request_id=%s",
                    (request["action_request_id"],),
                )[0]["state"]
                == "unknown"
            ):
                break
            time.sleep(0.1)
        else:
            raise AssertionError("Restarted worker did not materialize unknown")
        run_bot("catalog", directory, "python", True)
        assert (
            owner.call("GET", "/v1/action-requests/" + request["action_request_id"])["state"]
            == "confirmed"
        )
        for k, c in channels.items():
            # The extra news resource is unbound, so published records remain unchanged.
            assert (
                owner.call("GET", "/v1/channels/" + c["slug"])["records"] == snapshots[k]["records"]
            )
        owner.call(
            "DELETE", "/v1/bots/" + identity["bot_id"] + "/keys/" + identity["key_id"], expected=204
        )
        try:
            news.send_message(message)
        except APIError as error:
            assert error.status == 401
        else:
            raise AssertionError("Revoked key replay succeeded")
        return {
            "result": "PASS",
            "crash_boundaries": phases,
            "api_restarts": 5,
            "worker_restart": True,
            "duplicate_writers": 8,
            "one_receipt_outbox": True,
            "http_outbox_failure_rolled_back": True,
            "one_demo_effect_per_request": True,
            "private_read_denial": True,
            "revoked_key_replay_denial": True,
            "ui_tested": False,
        }
    finally:
        owner.retire_test_workspace()
        for kind in ("catalog", "news"):
            (directory / (kind + ".env")).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-file", type=Path)
    parser.add_argument("--report", type=Path, default=Path(".local/backend-faults.json"))
    args = parser.parse_args()
    lab = Lab(args.connection_file)
    try:
        lab.open()
        result = faults(lab)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
    finally:
        lab.close()


if __name__ == "__main__":
    main()
