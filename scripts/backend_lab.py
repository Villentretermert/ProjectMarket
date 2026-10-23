"""Disposable PostgreSQL schema and real API/worker processes for backend acceptance."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import IO, Any
from urllib.request import urlopen
from uuid import uuid4

import psycopg
from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.migrate import migrate
from psycopg import sql
from pydantic import SecretStr


class Lab:
    def __init__(self, connection_file: Path | None):
        url = (
            json.loads(connection_file.read_text())["url"]
            if connection_file
            else os.environ.get("MARKETOB_TEST_DATABASE_URL")
        )
        if not url:
            raise RuntimeError(
                "Set MARKETOB_TEST_DATABASE_URL or --connection-file for a test database."
            )
        self.url = SecretStr(url)
        self.schema = "lab_" + uuid4().hex
        self.directory = Path(".local") / self.schema
        self.directory.mkdir(parents=True)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.origin = f"http://127.0.0.1:{port}"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("MARKETOB_")}
        self.env.update(
            MARKETOB_DATABASE_URL=url,
            MARKETOB_DATABASE_SCHEMA=self.schema,
            MARKETOB_PORT=str(port),
            MARKETOB_HOST="127.0.0.1",
            MARKETOB_ALLOWED_ORIGINS=json.dumps([self.origin]),
            MARKETOB_AUTH_RATE_LIMIT="1000",
            MARKETOB_WRITE_RATE_LIMIT="10000",
            MARKETOB_LOG_DIRECTORY=str((self.directory / "logs").resolve()),
            TMP=str(self.directory.resolve()),
            TEMP=str(self.directory.resolve()),
            TMPDIR=str(self.directory.resolve()),
        )
        # Only provisioning limits differ; ingest/read/action quotas retain normal defaults.
        self.database = Database(
            Settings(_env_file=None, database_url=self.url, database_schema=self.schema)
        )
        self.processes: dict[str, subprocess.Popen[bytes]] = {}
        self.logs: list[IO[bytes]] = []

    def open(self) -> None:
        with psycopg.connect(
            self.url.get_secret_value(), autocommit=True, connect_timeout=5
        ) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        migrate(self.database)
        self.start("api")

    def start(self, kind: str) -> None:
        if kind in self.processes:
            raise RuntimeError("Stop the owned process before restarting it.")
        log = (self.directory / (kind + ".log")).open("ab")
        self.logs.append(log)
        command = [
            sys.executable,
            "-m",
            "marketob_api" + (".maintenance" if kind == "worker" else ""),
        ]
        process = subprocess.Popen(
            command,
            env=self.env,
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.processes[kind] = process
        if kind == "api":
            for _ in range(120):
                try:
                    with urlopen(self.origin + "/health/ready", timeout=1) as response:
                        if response.status == 200:
                            return
                except OSError:
                    if process.poll() is not None:
                        break
                    time.sleep(0.25)
            raise RuntimeError("Temporary API failed readiness; inspect private lab log.")

    def stop(self, kind: str) -> None:
        process = self.processes.pop(kind, None)
        if process is None:
            return
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                process.kill()
        process.wait(timeout=15)

    def query(self, query: str, params: tuple[Any, ...] = ()) -> Any:
        with self.database.transaction() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall() if cursor.description else None

    def close(self) -> None:
        for kind in list(self.processes):
            self.stop(kind)
        for log in self.logs:
            log.close()
        assert self.schema.startswith("lab_") and len(self.schema) == 36
        with psycopg.connect(
            self.url.get_secret_value(), autocommit=True, connect_timeout=5
        ) as conn:
            conn.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema))
            )
