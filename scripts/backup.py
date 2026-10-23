"""Consistent PostgreSQL archives; restore only into a new database, never overwrite."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from marketob_api.config import Settings
from marketob_api.migrate import migration_checksums
from psycopg.conninfo import conninfo_to_dict
from pydantic import SecretStr


class BackupError(RuntimeError):
    """Only fixed, credential-free operator messages may escape the CLI."""


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value):
        raise BackupError("Use a lower-case database/schema identifier of at most 63 characters.")
    return value


def migrations() -> dict[str, str]:
    return migration_checksums()


@dataclass
class Postgres:
    url: SecretStr | None = None
    pg_bin: Path | None = None
    compose: bool = False
    compose_files: tuple[str, ...] = ("compose.yaml",)
    database: str = "marketob"
    wsl_distribution: str | None = None
    project_name: str | None = None
    env_file: str | None = None

    def command(
        self, program: str, args: list[str], database: str | None
    ) -> tuple[list[str], dict[str, str]]:
        environment = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
        if self.compose:
            command = ["docker", "compose"]
            if self.wsl_distribution:
                command = ["wsl", "-d", self.wsl_distribution, "--", *command]
            if self.project_name:
                command += ["--project-name", self.project_name]
            if self.env_file:
                command += ["--env-file", self.env_file]
            for name in self.compose_files:
                command += ["-f", name]
            return command + ["exec", "-T", "db", program, "-U", "marketob", *args], environment
        if self.url is None:
            raise BackupError("Configure a local database URL or use --compose.")
        mapping = {
            "host": "PGHOST",
            "hostaddr": "PGHOSTADDR",
            "port": "PGPORT",
            "dbname": "PGDATABASE",
            "user": "PGUSER",
            "password": "PGPASSWORD",
            "sslmode": "PGSSLMODE",
            "sslrootcert": "PGSSLROOTCERT",
            "sslcert": "PGSSLCERT",
            "sslkey": "PGSSLKEY",
            "connect_timeout": "PGCONNECT_TIMEOUT",
        }
        parameters = conninfo_to_dict(self.url.get_secret_value())
        if parameters.keys() - mapping.keys():
            raise BackupError(
                "Unsupported connection options; use an explicit host/port/user/database URL."
            )
        environment.update({mapping[k]: str(v) for k, v in parameters.items() if v is not None})
        environment.update(PGCONNECT_TIMEOUT="5", PGCLIENTENCODING="UTF8")
        if database:
            environment["PGDATABASE"] = identifier(database)
        executable = str(self.pg_bin / program) if self.pg_bin else program
        return [executable, *args], environment

    def run(
        self,
        program: str,
        args: list[str],
        *,
        database: str | None = None,
        data: bytes | None = None,
        source: BinaryIO | None = None,
        output: BinaryIO | None = None,
    ) -> bytes:
        command, environment = self.command(program, args, database)
        try:
            result = subprocess.run(
                command,
                env=environment,
                input=data,
                stdin=source,
                stdout=output or subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=900,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError, subprocess.TimeoutExpired:
            raise BackupError(
                "PostgreSQL tool unavailable or timed out; check the local prerequisites."
            ) from None
        if result.returncode:
            # PostgreSQL stderr may contain URLs, private values or SQL fragments.
            raise BackupError(
                f"{program} failed (exit {result.returncode}); no database was overwritten."
            )
        if result.stderr.strip():
            raise BackupError(
                f"{program} emitted diagnostics; the operation is not accepted as verified."
            )
        return result.stdout or b""

    def query(self, query: str, database: str | None = None) -> Any:
        value = (
            self.run(
                "psql",
                ["-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-d", database or self.database],
                database=database,
                data=query.encode("utf-8"),
            )
            .decode("utf-8")
            .strip()
        )
        return json.loads(value) if value else None

    def info(self, schema: str, database: str | None = None) -> dict[str, Any]:
        schema = identifier(schema)
        result = self.query(
            "SELECT json_build_object('postgres_major',"
            "current_setting('server_version_num')::int/10000,"
            "'migrations',(SELECT json_object_agg(name,checksum) "
            f"FROM {schema}.schema_migrations));",
            database,
        )
        if not isinstance(result, dict) or result.get("migrations") != migrations():
            raise BackupError(
                "Database migrations do not match this checkout; use the matching release."
            )
        return result


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def create_backup(pg: Postgres, directory: Path, schema: str = "public") -> dict[str, Any]:
    schema = identifier(schema)
    before = pg.info(schema)
    # Exclusive directory creation leaves existing backups untouched, including incomplete ones.
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    archive = directory / "database.dump"
    with archive.open("xb") as stream:
        archive.chmod(0o600)
        pg.run(
            "pg_dump",
            [
                "-d",
                pg.database,
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--schema=" + schema,
                "--strict-names",
            ],
            output=stream,
        )
        stream.flush()
        os.fsync(stream.fileno())
    if pg.info(schema) != before:
        raise BackupError(
            "Schema changed during backup; keep upgrades stopped and retry in a new directory."
        )
    manifest = {
        "format": "marketob-postgres-backup-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "schema": schema,
        **before,
        "archive": "database.dump",
        "sha256": digest(archive),
        "bytes": archive.stat().st_size,
    }
    with (directory / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return manifest


def verify_backup(directory: Path) -> dict[str, Any]:
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        archive = directory / "database.dump"
        if (
            not isinstance(manifest, dict)
            or manifest.get("format") != "marketob-postgres-backup-v1"
            or manifest.get("archive") != "database.dump"
            or manifest.get("bytes") != archive.stat().st_size
            or manifest.get("sha256") != digest(archive)
            or manifest.get("migrations") != migrations()
            or not isinstance(manifest.get("schema"), str)
            or type(manifest.get("postgres_major")) is not int
        ):
            raise ValueError
        identifier(manifest["schema"])
        return manifest
    except OSError, ValueError, TypeError:
        raise BackupError(
            "Incomplete, corrupt or incompatible backup; destination was not touched."
        ) from None


def restore_backup(pg: Postgres, directory: Path, destination: str) -> dict[str, Any]:
    destination = identifier(destination)
    if destination in {pg.database, "postgres", "template0", "template1"}:
        raise BackupError(
            "Restore requires a new database name, distinct from the source and system databases."
        )
    manifest = verify_backup(directory)
    major = pg.query("SELECT current_setting('server_version_num')::int/10000;")
    if major != manifest["postgres_major"]:
        raise BackupError("This pilot restore requires the same PostgreSQL major version.")
    # CREATE DATABASE atomically refuses an existing destination, even with concurrent restores.
    pg.query(f'CREATE DATABASE "{destination}" TEMPLATE template0;')
    if manifest["schema"] == "public":
        # template0 includes an empty public schema; the archive recreates its definition.
        pg.query("DROP SCHEMA public;", destination)
    with (directory / "database.dump").open("rb") as stream:
        pg.run(
            "pg_restore",
            [
                "-d",
                destination,
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                "--single-transaction",
            ],
            database=destination,
            source=stream,
        )
    result = pg.info(manifest["schema"], destination)
    schema = manifest["schema"]
    valid = pg.query(
        f"SELECT to_json((SELECT watermark FROM {schema}.delivery_state) >= "
        f"COALESCE((SELECT max(delivery_sequence) FROM {schema}.change_outbox),0));",
        destination,
    )
    if valid is not True:
        raise BackupError(
            "Restored delivery state is inconsistent; do not connect the application."
        )
    return {"database": destination, "schema": schema, "postgres_major": result["postgres_major"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--compose", action="store_true", help="Use PostgreSQL tools inside the db container."
    )
    mode.add_argument(
        "--connection-file", type=Path, help="Private JSON file containing a url field."
    )
    parser.add_argument("--compose-file", action="append", help="Compose files in override order.")
    parser.add_argument("--pg-bin", type=Path, help="Directory containing PostgreSQL client tools.")
    parser.add_argument(
        "--wsl-distribution", help="Run Docker inside an existing WSL distribution."
    )
    parser.add_argument("--project-name", help="Existing Compose project name.")
    parser.add_argument("--env-file", help="Private Compose env file; relative to the repository.")
    parser.add_argument(
        "--database", help="Source database (default URL database or marketob in Compose)."
    )
    parser.add_argument("--schema", default="public")
    commands = parser.add_subparsers(dest="operation", required=True)
    for name in ("create", "verify", "restore"):
        action = commands.add_parser(name)
        action.add_argument("directory", type=Path)
        if name == "restore":
            action.add_argument("--new-database", required=True)
    args = parser.parse_args()
    try:
        if args.operation == "verify":
            result = verify_backup(args.directory)
        else:
            url = None
            if not args.compose:
                url = (
                    SecretStr(json.loads(args.connection_file.read_text())["url"])
                    if args.connection_file
                    else Settings().database_url
                )
            database = args.database or (
                conninfo_to_dict(url.get_secret_value()).get("dbname", "marketob")
                if url
                else "marketob"
            )
            pg = Postgres(
                url,
                args.pg_bin,
                args.compose,
                tuple(args.compose_file or ["compose.yaml"]),
                identifier(str(database)),
                args.wsl_distribution,
                args.project_name,
                args.env_file,
            )
            result = (
                create_backup(pg, args.directory, args.schema)
                if args.operation == "create"
                else restore_backup(pg, args.directory, args.new_database)
            )
        print(json.dumps({"operation": args.operation, "status": "ok", **result}))
    except BackupError as error:
        raise SystemExit(str(error)) from None
    except Exception:
        # Invalid settings and filesystem failures must not print credential-bearing values.
        raise SystemExit(
            "Backup operation failed; check configuration, paths and access locally."
        ) from None


if __name__ == "__main__":
    main()
