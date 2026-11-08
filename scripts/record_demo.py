"""Record the real My Space flow with synthetic data in a disposable database schema."""

import argparse
import json
import secrets
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from scripts.backend_lab import Lab
from scripts.docker_lab import DockerLab
from scripts.pilot_bots import bot_environment, provision, publish, run_bot
from scripts.smoke_ingestion import Http


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    backend = parser.add_mutually_exclusive_group()
    backend.add_argument("--connection-file", type=Path)
    backend.add_argument("--wsl", help="Use an isolated Docker delivery in this WSL distribution.")
    parser.add_argument("--release", default="local", help="Existing Docker image tag.")
    parser.add_argument("--output", type=Path, default=Path(".local/my-space-demo"))
    args = parser.parse_args()
    # Refuse to overwrite an earlier recording or its evidence.
    args.output.mkdir(parents=True, exist_ok=False)
    lab = DockerLab(args.wsl, args.release) if args.wsl else Lab(args.connection_file)
    try:
        lab.open()
        owner, reader = Http(lab.origin), Http(lab.origin)
        password = secrets.token_urlsafe(24)
        owner.csrf = owner.call(
            "POST",
            "/v1/auth/register",
            {
                "username": "demo_owner_" + uuid4().hex[:12],
                "password": password,
                "display_name": "Demo publisher",
            },
            expected=201,
        )["csrf_token"]
        credentials = {"username": "demo_reader_" + uuid4().hex[:12], "password": password}
        registration = reader.call(
            "POST",
            "/v1/auth/register",
            {**credentials, "display_name": "Alex · Demo"},
            expected=201,
        )
        reader.csrf = registration["csrf_token"]
        user_id = reader.call("GET", "/v1/auth/session")["user"]["user_id"]
        state = lab.directory / "bots"
        channels = provision(owner, state)
        for kind in ("catalog", "news"):
            run_bot(kind, state, "python", True)
        publish(owner, channels)
        for channel in channels.values():
            owner.call(
                "PUT",
                f"/v1/owner/channels/{channel['channel_id']}/grants/{user_id}",
                {},
                expected=204,
            )
        log = (lab.directory / "catalog.log").open("ab")
        lab.logs.append(log)
        lab.processes["catalog"] = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "marketob_bots.catalog",
                "--env-file",
                str(state / "catalog.env"),
            ],
            env=bot_environment(state),
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        # Synthetic login travels only through stdin; never record the authentication screen.
        subprocess.run(
            ["node", "apps/client/record-demo.mjs"],
            input=json.dumps(
                {
                    "origin": lab.origin,
                    "credentials": credentials,
                    "channels": channels,
                    "output": str(args.output.resolve()),
                }
            ),
            text=True,
            check=True,
            timeout=300,
        )
        actions = lab.query("SELECT state, count(*) AS n FROM action_requests GROUP BY state")
        assert len(actions) == 1 and actions[0]["n"] == 1 and actions[0]["state"] == "confirmed", (
            "The demonstration must create exactly one confirmed request"
        )
        evidence = args.output / "result.json"
        result = json.loads(evidence.read_text(encoding="utf-8"))
        result.update(database_requests=1, database_status="confirmed", synthetic_data=True)
        evidence.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("PASS: one real confirmed request; recording contains synthetic data only.")
    finally:
        lab.close()
    print("PASS: temporary API, bot and database schema removed.")


if __name__ == "__main__":
    main()
