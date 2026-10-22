"""Apply immutable SQL migrations transactionally, serialized across API processes."""

import hashlib
import secrets
from importlib.resources import files

from marketob_api.config import Settings
from marketob_api.database import Database


def migrate(database: Database) -> list[str]:
    applied: list[str] = []
    with database.transaction() as connection:
        connection.execute("SELECT pg_advisory_xact_lock(62781405001)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz DEFAULT now())"
        )
        existing = {
            row["name"]: row["checksum"]
            for row in connection.execute("SELECT name, checksum FROM schema_migrations")
        }
        for resource in sorted(
            files("marketob_api").joinpath("migrations").iterdir(), key=lambda x: x.name
        ):
            if not resource.name.endswith(".sql"):
                continue
            text = resource.read_text(encoding="utf-8")
            digest = hashlib.sha256(text.replace("\r\n", "\n").encode()).hexdigest()
            if resource.name in existing:
                if existing[resource.name] != digest:
                    raise RuntimeError(
                        "Applied migration changed; restore it and add a new migration."
                    )
                continue
            connection.execute(text)
            connection.execute(
                "INSERT INTO schema_migrations(name, checksum) VALUES (%s, %s)",
                (resource.name, digest),
            )
            applied.append(resource.name)
        connection.execute(
            "INSERT INTO server_keys(purpose, secret) VALUES ('cursor', %s) "
            "ON CONFLICT (purpose) DO NOTHING",
            (secrets.token_bytes(32),),
        )
    return applied


def main() -> None:
    names = migrate(Database(Settings()))
    print("Migrations applied: " + (", ".join(names) or "already current"))


if __name__ == "__main__":
    main()
