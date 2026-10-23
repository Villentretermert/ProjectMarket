"""Disposable Docker delivery stack, isolated from the owner's running pilot."""

import json
import os
import secrets
import socket
import subprocess
from pathlib import Path
from uuid import uuid4

from marketob_api.config import Settings
from marketob_api.database import Database
from pydantic import SecretStr

from scripts.backend_lab import Lab


class DockerLab(Lab):
    def __init__(self, distribution: str, release: str):
        self.directory = Path(".local") / ("docker_load_" + uuid4().hex)
        self.directory.mkdir(parents=True)
        self.project = "marketob-load-" + uuid4().hex[:12]
        self.schema = "public"  # This project owns an entirely disposable database/volume.
        with socket.socket() as api_listener, socket.socket() as database_listener:
            api_listener.bind(("127.0.0.1", 0))
            database_listener.bind(("127.0.0.1", 0))
            port = api_listener.getsockname()[1]
            database_port = database_listener.getsockname()[1]
        password = secrets.token_urlsafe(32)
        self.origin = f"http://127.0.0.1:{port}"
        self.url = SecretStr(f"postgresql://marketob:{password}@127.0.0.1:{database_port}/marketob")
        self.env = dict(os.environ)
        self.database = Database(
            Settings(_env_file=None, database_url=self.url, database_schema=self.schema)
        )
        self.processes = {}
        self.logs = []
        env_path = self.directory / "docker.env"
        env_path.write_text(
            f"POSTGRES_PASSWORD={password}\nMARKETOB_PORT={port}\n"
            f"MARKETOB_RELEASE={release}\nMARKETOB_AUTH_RATE_LIMIT=1000\n"
            f"MARKETOB_ALLOWED_ORIGINS={json.dumps([self.origin])}\n",
            encoding="utf-8",
        )
        override = self.directory / "compose.json"
        override.write_text(
            json.dumps(
                {
                    "services": {
                        "db": {
                            "ports": [f"127.0.0.1:{database_port}:5432"],
                            "mem_limit": "2g",
                            "pids_limit": 256,
                        },
                        "api": {
                            "mem_limit": "512m",
                            "pids_limit": 128,
                            "environment": {"MARKETOB_WRITE_RATE_LIMIT": "10000"},
                        },
                        "maintenance": {"mem_limit": "256m", "pids_limit": 128},
                    }
                }
            ),
            encoding="utf-8",
        )
        self.command = [
            "wsl",
            "-d",
            distribution,
            "--",
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--env-file",
            env_path.as_posix(),
            "-f",
            "compose.yaml",
            "-f",
            override.as_posix(),
        ]

    def run(self, *arguments: str, timeout: int = 180) -> bytes:
        result = subprocess.run(
            [*self.command, *arguments],
            capture_output=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            (self.directory / "docker-error.log").write_bytes(result.stderr)
            raise RuntimeError("Disposable Docker command failed; inspect its private lab log.")
        return result.stdout

    def open(self) -> None:
        self.start("api")
        # Fail before provisioning if WSL localhost forwarding is unavailable.
        with self.database.transaction() as connection:
            connection.execute("SELECT 1")

    def start(self, kind: str) -> None:
        service = {"api": "api", "worker": "maintenance"}[kind]
        self.run("up", "--detach", "--no-build", "--wait", "--wait-timeout", "120", service)

    def stop(self, kind: str) -> None:
        if kind == "browser":
            super().stop(kind)
        else:
            self.run("stop", {"api": "api", "worker": "maintenance"}[kind])

    def capture_logs(self) -> None:
        directory = self.directory / "logs"
        directory.mkdir(exist_ok=True)
        for service, name in (("api", "api"), ("maintenance", "worker")):
            exported = self.run("logs", "--no-color", "--no-log-prefix", service)
            # Preserve line boundaries and the metrics reader's bounded-file contract.
            chunk = bytearray()
            index = 0
            for line in exported.splitlines(keepends=True):
                if len(chunk) + len(line) > 10 * 1024 * 1024 and chunk:
                    (directory / f"{name}.jsonl.{index}").write_bytes(chunk)
                    index += 1
                    chunk.clear()
                chunk.extend(line)
            (directory / f"{name}.jsonl.{index}").write_bytes(chunk)

    def close(self) -> None:
        for kind in list(self.processes):
            super().stop(kind)
        # Never use the owner's project name here; only this newly created fixture is removed.
        assert self.project.startswith("marketob-load-") and len(self.project) == 26
        self.run("down", "--volumes", "--remove-orphans")
