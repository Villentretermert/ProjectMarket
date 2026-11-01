"""Exercise the actual API C runtime against a disposable TLS PostgreSQL container."""

import argparse
import json
import os
import secrets
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4


def inside() -> None:
    import psycopg
    from marketob_api.config import Settings
    from marketob_api.database import Database, Pools
    from psycopg.types.json import Jsonb
    from pydantic import SecretStr

    assert psycopg.pq.__impl__ == "c"
    assert psycopg.pq.version() == psycopg.pq.__build_version__ == 180006
    parameters = dict(sslmode="verify-full", sslrootcert="/certs/ca.crt", gssencmode="disable")
    with psycopg.connect(psycopg.conninfo.make_conninfo(**parameters)) as connection:
        assert connection.pgconn.ssl_in_use
        connection.execute("CREATE TABLE driver_probe (id int primary key, body jsonb)")
        for number in range(4):
            assert connection.execute("SELECT %s::jsonb", (Jsonb({"n": number}),)).fetchone() == (
                {"n": number},
            )
    for invalid in (
        {"sslrootcert": "/certs/other.crt"},
        {"sslrootcert": "/certs/missing.crt"},
        {"host": "wrong.test"},
    ):
        try:
            psycopg.connect(psycopg.conninfo.make_conninfo(**(parameters | invalid))).close()
        except psycopg.OperationalError:
            pass
        else:
            raise AssertionError("Invalid TLS peer was accepted")
    # Verify system trust selection, scoped to this fixture process only.
    os.environ["SSL_CERT_FILE"] = "/certs/ca.crt"
    with psycopg.connect(
        psycopg.conninfo.make_conninfo(**(parameters | {"sslrootcert": "system"}))
    ) as connection:
        assert connection.pgconn.ssl_in_use
    with psycopg.connect(sslmode="prefer") as connection:
        assert connection.execute("SELECT 1").fetchone() == (1,)

    dsn = psycopg.conninfo.make_conninfo(**parameters)
    settings = Settings(
        _env_file=None,
        database_url=SecretStr(
            "postgresql://postgres@db.test/postgres?"
            + "sslmode=verify-full&sslrootcert=/certs/ca.crt&gssencmode=disable"
        ),
    )
    pools = Pools(settings)
    settings._database_pools = pools
    database = Database(settings)
    try:
        pools.primary.wait(timeout=10)
        pools.auxiliary.wait(timeout=10)
        with database.transaction() as transaction:
            transaction.execute("INSERT INTO driver_probe VALUES (1, %s)", (Jsonb({"ok": True}),))
        try:
            with database.transaction(auxiliary=True) as transaction:
                transaction.execute("INSERT INTO driver_probe VALUES (2, '{}'::jsonb)")
                raise ValueError("rollback control")
        except ValueError:
            pass
        with database.transaction(auxiliary=True) as transaction:
            assert transaction.execute("SELECT count(*) AS n FROM driver_probe").fetchone() == {
                "n": 1
            }
        try:
            with database.transaction() as transaction:
                transaction.execute("SET LOCAL statement_timeout=100")
                transaction.execute("SELECT pg_sleep(3)")
        except psycopg.errors.QueryCanceled:
            pass
        else:
            raise AssertionError("Statement timeout did not cancel query")
        with database.transaction() as transaction:
            assert transaction.execute("SELECT 1 AS n").fetchone() == {"n": 1}
        # Kill both idle primary connections; checkout health checks must replace them.
        with pools.primary.connection() as first, pools.primary.connection() as second:
            pids = [first.info.backend_pid, second.info.backend_pid]
        with psycopg.connect(dsn, autocommit=True) as administrator:
            for pid in pids:
                administrator.execute("SELECT pg_terminate_backend(%s)", (pid,))
        with database.transaction() as transaction:
            assert transaction.execute("SELECT 1 AS n").fetchone() == {"n": 1}
    finally:
        pools.close()
        settings._database_pools = None
    # Also exercise the non-pool path used by migration and maintenance.
    with database.transaction() as transaction:
        assert transaction.execute("SELECT count(*) AS n FROM driver_probe").fetchone() == {"n": 1}
    with psycopg.connect(dsn) as connection:
        errors: list[Exception] = []

        def cancel() -> None:
            try:
                connection.cancel_safe(timeout=3)
            except Exception as error:
                errors.append(error)

        timer = threading.Timer(0.2, cancel)
        timer.start()
        started = time.monotonic()
        try:
            connection.execute("SET statement_timeout=5000")
            connection.execute("SELECT pg_sleep(10)")
        except psycopg.errors.QueryCanceled:
            connection.rollback()
        else:
            raise AssertionError("Cancellation failed")
        finally:
            timer.join(timeout=5)
        assert not timer.is_alive() and not errors and time.monotonic() - started < 4
        assert connection.execute("SELECT 1").fetchone() == (1,)
    print(
        json.dumps(
            {
                "result": "PASS",
                "implementation": "c",
                "libpq": 180006,
                "checks": [
                    "TLS verify-full",
                    "wrong CA rejected",
                    "missing CA rejected",
                    "wrong hostname rejected",
                    "system CA",
                    "default connection",
                    "JSONB parameters",
                    "primary/auxiliary pools",
                    "commit/rollback",
                    "statement timeout",
                    "terminated connections recovered",
                    "non-pool transaction",
                    "cancel_safe",
                ],
            }
        )
    )


CERTIFICATES = """set -eu
cd /certs
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=fixture-ca \\
  -keyout ca.key -out ca.crt 2>/dev/null
openssl req -newkey rsa:2048 -nodes -subj /CN=db.test -keyout server.key -out server.csr 2>/dev/null
printf 'subjectAltName=DNS:db.test\\nextendedKeyUsage=serverAuth\\n' > server.ext
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 1 \\
  -extfile server.ext -out server.crt 2>/dev/null
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=untrusted-ca \\
  -keyout other.key -out other.crt 2>/dev/null
chown postgres:postgres server.key
chmod 600 *.key
chmod 644 *.crt
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--api-image", default="marketob-api:local")
    parser.add_argument("--db-image", default="marketob-db:local")
    parser.add_argument("--wsl")
    args = parser.parse_args()
    if args.inside:
        inside()
        return
    prefix = ["wsl", "-d", args.wsl, "--exec", "docker"] if args.wsl else ["docker"]
    name = "marketob-driver-" + uuid4().hex[:12]
    password = secrets.token_urlsafe(32)
    created: list[tuple[str, str]] = []

    def docker(*parts: str, source: str | None = None) -> str:
        result = subprocess.run(
            prefix + list(parts),
            input=source.encode("utf-8") if source is not None else None,
            capture_output=True,
            timeout=120,
        )
        if result.returncode:
            # Never include argument vectors: they may contain fixture credentials.
            raise RuntimeError(
                result.stderr.decode("utf-8", "replace").replace(password, "[redacted]")
            )
        return result.stdout.decode("utf-8", "replace")

    try:
        docker("network", "create", "--internal", name)
        created.append(("network", name))
        docker("volume", "create", name)
        created.append(("volume", name))
        docker(
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "-v",
            f"{name}:/certs",
            "--entrypoint",
            "sh",
            args.db_image,
            source=CERTIFICATES,
        )
        docker(
            "run",
            "-d",
            "--name",
            name,
            "--network",
            name,
            "--network-alias",
            "db.test",
            "--network-alias",
            "wrong.test",
            "--tmpfs",
            "/var/lib/postgresql",
            "-v",
            f"{name}:/certs:ro",
            "-e",
            f"POSTGRES_PASSWORD={password}",
            args.db_image,
            "postgres",
            "-c",
            "ssl=on",
            "-c",
            "ssl_cert_file=/certs/server.crt",
            "-c",
            "ssl_key_file=/certs/server.key",
        )
        created.append(("container", name))
        for _ in range(60):
            try:
                docker("exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres")
                break
            except RuntimeError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Disposable TLS database did not become ready")
        print(
            docker(
                "run",
                "--rm",
                "-i",
                "--read-only",
                "--network",
                name,
                "-v",
                f"{name}:/certs:ro",
                "-e",
                "PGHOST=db.test",
                "-e",
                "PGUSER=postgres",
                "-e",
                "PGDATABASE=postgres",
                "-e",
                "PGCONNECT_TIMEOUT=3",
                "-e",
                f"PGPASSWORD={password}",
                "--entrypoint",
                "python",
                args.api_image,
                "-",
                "--inside",
                source=Path(__file__).read_text(encoding="utf-8"),
            ).strip()
        )
    finally:
        for kind, resource in reversed(created):
            docker(kind, "rm", *(["--force"] if kind == "container" else []), resource)


if __name__ == "__main__":
    main()
