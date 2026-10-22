"""Short PostgreSQL transactions, committed before an endpoint returns success."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from marketob_api.config import Settings
from marketob_api.errors import ApiError

type Connection = psycopg.Connection[dict[str, Any]]


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        if self.settings.database_url is None:
            raise ApiError(503, "storage_unavailable", "Local storage is not configured.")
        with psycopg.connect(
            self.settings.database_url.get_secret_value(),
            row_factory=dict_row,
            connect_timeout=self.settings.database_timeout_seconds,
            options=(
                "-c statement_timeout=5000 -c lock_timeout=3000 "
                f"-c search_path={self.settings.database_schema}"
            ),
        ) as connection:
            yield connection
