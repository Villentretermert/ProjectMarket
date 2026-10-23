"""Liveness stays independent of PostgreSQL; readiness checks a real query."""

from typing import Literal

import psycopg
from pydantic import BaseModel

from marketob_api.config import Settings
from marketob_api.migrate import migration_checksums

type DatabaseStatus = Literal["ok", "not_configured", "unavailable"]


class LiveStatus(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["marketob-api"] = "marketob-api"
    version: str


class ReadyStatus(BaseModel):
    status: Literal["ready", "not_ready"]
    database: DatabaseStatus


def database_status(settings: Settings) -> DatabaseStatus:
    if settings.database_url is None:
        return "not_configured"
    try:
        with psycopg.connect(
            settings.database_url.get_secret_value(),
            connect_timeout=settings.database_timeout_seconds,
            options=(
                f"-c statement_timeout={settings.database_timeout_seconds * 1000} "
                f"-c search_path={settings.database_schema}"
            ),
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT name, checksum FROM schema_migrations")
                return "ok" if dict(cursor.fetchall()) == migration_checksums() else "unavailable"
    except psycopg.Error:
        # Connection errors can contain credentials or hostnames: return only a status.
        return "unavailable"
