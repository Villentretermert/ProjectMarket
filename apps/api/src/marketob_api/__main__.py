"""Loopback by default; containers override MARKETOB_HOST explicitly."""

import sys

import uvicorn
from pydantic import ValidationError

from marketob_api.app import create_app
from marketob_api.config import Settings
from marketob_api.observability import configure_logging


def main() -> None:
    try:
        settings = Settings()
    except ValidationError:
        print("Invalid MarkeTOB configuration; check .env against .env.example.", file=sys.stderr)
        raise SystemExit(2) from None
    configure_logging(settings.log_level, settings.log_directory)
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        proxy_headers=False,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
