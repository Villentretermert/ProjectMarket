"""Run isolated-schema integration tests against an explicitly configured local database."""

import os
import subprocess
import sys
from urllib.parse import quote

from dotenv import dotenv_values


def main() -> None:
    environment = dict(os.environ)
    if "MARKETOB_TEST_DATABASE_URL" not in environment:
        password = dotenv_values(".env").get("POSTGRES_PASSWORD")
        if not password:
            raise SystemExit("Set MARKETOB_TEST_DATABASE_URL or create the Compose test .env.")
        environment["MARKETOB_TEST_DATABASE_URL"] = (
            f"postgresql://marketob:{quote(password, safe='')}@127.0.0.1:55432/marketob"
        )
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-m", "pytest", "-q", "-m", "integration"], env=environment
        )
    )


if __name__ == "__main__":
    main()
