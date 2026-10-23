"""Loopback by default; containers override MARKETOB_HOST explicitly."""

import sys

import uvicorn
from fastapi import FastAPI
from pydantic import ValidationError

from marketob_api.app import create_app
from marketob_api.config import Settings
from marketob_api.observability import configure_logging


def configuration() -> Settings:
    try:
        return Settings()
    except ValidationError:
        print("Invalid MarkeTOB configuration; check .env against .env.example.", file=sys.stderr)
        raise SystemExit(2) from None


def application() -> FastAPI:
    # Each spawned worker owns its pools and logger; shared state remains in PostgreSQL.
    settings = configuration()
    configure_logging(settings.log_level, settings.log_directory)
    return create_app(settings)


def main() -> None:
    settings = configuration()
    configure_logging(settings.log_level, settings.log_directory)
    uvicorn.run(
        "marketob_api.__main__:application",
        factory=True,
        workers=settings.api_workers,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        proxy_headers=False,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
