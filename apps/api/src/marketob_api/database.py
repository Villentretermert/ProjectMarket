"""Short PostgreSQL transactions, committed before an endpoint returns success."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from marketob_api.config import Settings
from marketob_api.errors import ApiError

type Connection = psycopg.Connection[dict[str, Any]]


class Pools:
    """Separate auxiliary capacity prevents nested quota/dispatch transactions starving."""

    def __init__(self, settings: Settings):
        assert settings.database_url is not None
        kwargs = {
            "row_factory": dict_row,
            "connect_timeout": settings.database_timeout_seconds,
            "options": "-c statement_timeout=5000 -c lock_timeout=3000 "
            f"-c search_path={settings.database_schema}",
        }
        self.primary = ConnectionPool[Connection](
            settings.database_url.get_secret_value(),
            kwargs=kwargs,
            min_size=2,
            max_size=32 // settings.api_workers,
            open=True,
            timeout=3,
            max_waiting=40,
            check=ConnectionPool.check_connection,
        )
        self.auxiliary = ConnectionPool[Connection](
            settings.database_url.get_secret_value(),
            kwargs=kwargs,
            min_size=2,
            max_size=8 // settings.api_workers,
            open=True,
            timeout=3,
            max_waiting=40,
            check=ConnectionPool.check_connection,
        )

    def close(self) -> None:
        self.primary.close()
        self.auxiliary.close()


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings

    @contextmanager
    def transaction(self, *, auxiliary: bool = False) -> Iterator[Connection]:
        if self.settings.database_url is None:
            raise ApiError(503, "storage_unavailable", "Local storage is not configured.")
        pools = self.settings._database_pools
        if isinstance(pools, Pools):
            pool = pools.auxiliary if auxiliary else pools.primary
            with pool.connection() as connection:
                yield connection
            return
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
