"""Real browser + API + independent bots in a disposable PostgreSQL schema."""

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from scripts.backend_lab import Lab
from scripts.pilot_bots import bot_environment, provision, publish, run_bot
from scripts.smoke_ingestion import Http


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-file", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".local/web-evidence"))
    args = parser.parse_args()
    lab = Lab(args.connection_file)
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        lab.open()
        owner = Http(lab.origin)
        credentials = {"username": "web_" + uuid4().hex[:20], "password": secrets.token_urlsafe(24)}
        owner.csrf = owner.call(
            "POST",
            "/v1/auth/register",
            {**credentials, "display_name": "Alex · Pilot"},
            expected=201,
        )["csrf_token"]
        state = lab.directory / "bots"
        channels = provision(owner, state)
        for kind in ("catalog", "news"):
            run_bot(kind, state, "python", True)
        publish(owner, channels)
        lab.query(
            "UPDATE bot_keys SET expires_at=now()+interval '6 days' WHERE bot_id=%s",
            (channels["catalog"]["bot_id"],),
        )
        lab.query(
            "UPDATE bot_keys SET expires_at=now()-interval '1 day' WHERE bot_id=%s",
            (channels["news"]["bot_id"],),
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
        # Only synthetic test login and public channel IDs go to the browser process stdin.
        result = subprocess.run(
            ["node", "apps/client/acceptance.mjs"],
            input=json.dumps(
                {
                    "origin": lab.origin,
                    "credentials": credentials,
                    "channels": channels,
                    "output": str(args.output.resolve()),
                }
            ),
            text=True,
            check=False,
            env=dict(os.environ),
            timeout=240,
        )
        if result.returncode:
            raise SystemExit(result.returncode)
        counts = lab.query("SELECT count(*) AS n FROM action_requests")
        assert counts[0]["n"] == 4, "Three channel requests plus one My Space request; no duplicate"
        print("PASS: real Web/API/bot browser acceptance; disposable state removed.")
    finally:
        lab.close()


if __name__ == "__main__":
    main()
