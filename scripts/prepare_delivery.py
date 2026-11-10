"""Create new private settings for a received kit; never start or replace a stack."""

import argparse
import os
import secrets
from pathlib import Path
from uuid import uuid4


def prepare(directory: Path, port: int, https_port: int) -> str:
    if port == https_port or any(not 1024 <= p <= 65535 for p in (port, https_port)):
        raise ValueError("Choose two distinct ports between 1024 and 65535")
    directory.mkdir(parents=True, exist_ok=False)
    project = "marketob-received-" + uuid4().hex[:12]
    # Exclusive creation preserves credentials from an earlier initialization.
    with os.fdopen(
        os.open(directory / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
        "w",
        encoding="utf-8",
    ) as stream:
        stream.write(
            f"COMPOSE_PROJECT_NAME={project}\nPOSTGRES_PASSWORD={secrets.token_urlsafe(32)}\n"
        )
        stream.write(f"MARKETOB_PORT={port}\nMARKETOB_HTTPS_PORT={https_port}\n")
        stream.write(
            f'MARKETOB_ALLOWED_ORIGINS=["http://127.0.0.1:{port}","https://localhost:{https_port}"]\n'
        )
    return project


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18000)
    parser.add_argument("--https-port", type=int, default=18443)
    args = parser.parse_args()
    name = prepare(args.output.resolve(), args.port, args.https_port)
    print("Created private settings for " + name + ". Follow README.md to start it.")


if __name__ == "__main__":
    main()
