"""Run isolated-schema integration tests against an explicitly configured local database."""

import argparse
import os
import subprocess
import sys
from urllib.parse import quote

from dotenv import dotenv_values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend", action="store_true", help="Run process faults and a 60s paced baseline"
    )
    parser.add_argument("--web", action="store_true", help="Run real browser/API/bot acceptance")
    args = parser.parse_args()
    environment = dict(os.environ)
    if "MARKETOB_TEST_DATABASE_URL" not in environment:
        password = dotenv_values(".env").get("POSTGRES_PASSWORD")
        if not password:
            raise SystemExit("Set MARKETOB_TEST_DATABASE_URL or create the Compose test .env.")
        environment["MARKETOB_TEST_DATABASE_URL"] = (
            f"postgresql://marketob:{quote(password, safe='')}@127.0.0.1:55432/marketob"
        )
    if args.web:
        subprocess.run([sys.executable, "-m", "scripts.smoke_web"], env=environment, check=True)
        return
    if args.backend:
        subprocess.run([sys.executable, "-m", "scripts.smoke_backend"], env=environment, check=True)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.load_backend",
                "--seconds",
                "60",
                "--bots",
                "20",
                "--readers",
                "2",
            ],
            env=environment,
            check=True,
        )
        return
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-m", "pytest", "-q", "-m", "integration"], env=environment
        )
    )


if __name__ == "__main__":
    main()
