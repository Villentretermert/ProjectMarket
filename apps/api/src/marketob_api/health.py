"""Liveness stays independent of PostgreSQL; readiness checks a real query."""

from typing import Literal

import psycopg
from pydantic import BaseModel

from marketob_api.config import Settings

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
            options=f"-c statement_timeout={settings.database_timeout_seconds * 1000}",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return "ok" if cursor.fetchone() == (1,) else "unavailable"
    except psycopg.Error:
        # Connection errors can contain credentials or hostnames: return only a status.
        return "unavailable"
