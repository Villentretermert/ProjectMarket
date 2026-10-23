"""Backup safety and API fidelity across a real PostgreSQL database restore."""

import hashlib
import json
import os
import shutil
from collections.abc import Iterator
from dataclasses import replace
from importlib import import_module
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from marketob_api.config import Settings
from marketob_api.database import Database
from marketob_api.migrate import migrate, migration_checksums
from psycopg import sql
from pydantic import SecretStr

from scripts.backup import BackupError, Postgres, create_backup, restore_backup, verify_backup
from tests.test_actions import catalog, event_path, queue, report
from tests.test_bots import auth, create_bot, exchange
from tests.test_channels import path
from tests.test_identity import PASSWORD, business, client, register
from tests.test_ingestion import draft, message
from tests.test_personal_pages import body, create
from tests.test_sharing import share
from tests.test_updates import poll


def test_connection_values_never_enter_process_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGSERVICE", "unexpected-service")
    pg = Postgres(SecretStr("postgresql://pilot:synthetic-password@localhost:55432/pilot"))
    command, env = pg.command("pg_dump", ["-Fc"], None)
    assert command == ["pg_dump", "-Fc"]
    assert env["PGPASSWORD"] == "synthetic-password" and "PGSERVICE" not in env
    assert "synthetic-password" not in repr(pg)


def test_reject_incomplete_or_foreign_backup_before_running_tools(tmp_path: Path) -> None:
    pg = Postgres()
    with pytest.raises(BackupError, match="Incomplete"):
        restore_backup(pg, tmp_path, "new_database")
    with pytest.raises(BackupError, match="identifier"):
        restore_backup(pg, tmp_path, 'escape";drop')
    with pytest.raises(BackupError, match="new database"):
        restore_backup(pg, tmp_path, "marketob")


@pytest.fixture
def backup_lab() -> Iterator[tuple[Postgres, Settings, str]]:
    url = os.environ.get("MARKETOB_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Explicit PostgreSQL test server with CREATE DATABASE permission required")
    pg_bin = Path(os.environ["PG_BIN"]) if "PG_BIN" in os.environ else None
    compose = os.environ.get("BACKUP_COMPOSE") == "1"
    if not compose and not pg_bin and not shutil.which("pg_dump"):
        pytest.skip("PostgreSQL client tools required for native restore acceptance")
    source = "backup_test_" + uuid4().hex
    target = "restore_test_" + uuid4().hex
    parts = urlsplit(url)
    admin = Postgres(SecretStr(url), pg_bin, compose, database=parts.path.strip("/"))
    admin.query(f'CREATE DATABASE "{source}" TEMPLATE template0;')
    settings = Settings(
        _env_file=None,
        database_url=SecretStr(urlunsplit(parts._replace(path="/" + source))),
        auth_rate_limit=100,
    )
    try:
        migrate(Database(settings))
        yield replace(admin, database=source), settings, target
    finally:
        # Both names are unguessable, created only by this test; never touch the configured DB.
        with psycopg.connect(url, autocommit=True) as connection:
            for name in (source, target):
                assert name.startswith(("backup_test_", "restore_test_")) and len(name) == 44 + (
                    name.startswith("restore")
                )
                connection.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
                )


def target_settings(settings: Settings, name: str) -> Settings:
    assert settings.database_url
    parts = urlsplit(settings.database_url.get_secret_value())
    return settings.model_copy(
        update={"database_url": SecretStr(urlunsplit(parts._replace(path="/" + name)))}
    )


@pytest.mark.integration
def test_restore_preserves_private_sources_requests_layouts_keys_and_live_order(
    backup_lab: tuple[Postgres, Settings, str],
    tmp_path: Path,
) -> None:
    pg, settings, target = backup_lab
    with client(settings) as owner, client(settings) as bot, client(settings) as customer:
        register(owner, "alice")
        business(owner)
        key = exchange(bot, create_bot(owner)["registration_credential"])
        bot.headers.update(auth(key["api_key"]))
        source = draft(owner, key["bot_id"])
        catalog(owner, bot, source)
        uid = register(customer, "customer")
        assert owner.put(path(source, "/grants/" + uid), json={}).status_code == 204
        cid = source["channel_id"]
        assert customer.put("/v1/favorites/" + cid, json={}).status_code == 204
        assert (
            customer.put(
                "/v1/preferences/" + cid, json={"channel_id": cid, "events": ["catalog.changed"]}
            ).status_code
            == 200
        )
        page = create(customer, body(owner.get(path(source)).json()))
        link = share(customer, page)
        request = queue(customer, source)
        event = bot.get("/v1/bot/events").json()["items"][0]
        assert bot.post(event_path(event, "ack"), json={}).status_code == 200
        assert bot.post(event_path(event, "result"), json=report()).status_code == 200
        last = poll(customer)["next_cursor"]
        original_receipt = bot.post(
            "/v1/bot/messages", json=message(source, 2, "backup_news")
        ).json()
        before_updates = poll(customer, last)
        snapshot = customer.get("/v1/channels/" + source["slug"]).json()
        personal = customer.get("/v1/personal-pages/" + page["page_id"] + "/snapshot").json()
        folder = tmp_path / "backup"
        manifest = create_backup(pg, folder)
        assert manifest == verify_backup(folder)
        assert restore_backup(pg, folder, target)["database"] == target
        restored = target_settings(settings, target)
        assert migrate(Database(restored)) == []
        with (
            client(restored) as reader,
            client(restored) as restored_bot,
            client(restored) as stranger,
        ):
            login = reader.post(
                "/v1/auth/login", json={"username": "customer", "password": PASSWORD}
            )
            assert login.status_code == 200
            reader.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            assert reader.get("/v1/favorites").json()["items"][0]["channel_id"] == cid
            assert reader.get("/v1/preferences/" + cid).json()["events"] == ["catalog.changed"]
            assert (
                reader.get("/v1/action-requests/" + request["action_request_id"]).json()["state"]
                == "confirmed"
            )
            assert (
                reader.get("/v1/personal-pages/" + page["page_id"]).json()["layout"]
                == page["layout"]
            )
            assert (
                reader.post("/v1/template-imports/preview", json={"code": link["code"]}).status_code
                == 200
            )
            register(stranger, "stranger")
            assert stranger.get("/v1/channels/" + source["slug"]).status_code == 404
            restored_bot.headers.update(auth(key["api_key"]))
            assert (
                restored_bot.post("/v1/bot/messages", json=message(source, 2, "backup_news")).json()
                == original_receipt
            )
            # The copied session/cursor can resume; bootstrap did not reassign old update IDs.
            reader.cookies.clear()
            reader.cookies.update(customer.cookies)
            reader.headers["X-CSRF-Token"] = customer.headers["X-CSRF-Token"]
            assert poll(reader, last)["items"] == before_updates["items"]
            assert reader.get("/v1/channels/" + source["slug"]).json() == snapshot
            assert (
                reader.get("/v1/personal-pages/" + page["page_id"] + "/snapshot").json() == personal
            )
            new_cursor = poll(reader)["next_cursor"]
            assert (
                restored_bot.post(
                    "/v1/bot/messages", json=message(source, 3, "after_restore")
                ).status_code
                == 200
            )
            updates = poll(reader, new_cursor)
            assert int(updates["items"][0]["update_id"].split("_")[1]) > int(
                before_updates["items"][0]["update_id"].split("_")[1]
            )
            assert (
                queue(reader, source, "purchase_one")["action_request_id"]
                == request["action_request_id"]
            )
            assert (
                pg.query("SELECT count(*) FROM message_receipts WHERE message_id='after_restore';")
                == 0
            )


@pytest.mark.integration
def test_no_overwrite_corruption_migration_mismatch_and_failed_restore_are_safe(
    backup_lab: tuple[Postgres, Settings, str],
    tmp_path: Path,
) -> None:
    pg, settings, target = backup_lab
    folder = tmp_path / "backup"
    create_backup(pg, folder)
    with pytest.raises(FileExistsError):
        create_backup(pg, folder)
    with pytest.raises(BackupError, match="new database"):
        restore_backup(pg, folder, pg.database)
    pg.query(f'CREATE DATABASE "{target}" TEMPLATE template0;')
    pg.query("CREATE TABLE sentinel(value int); INSERT INTO sentinel VALUES(123);", target)
    with pytest.raises(BackupError, match="psql failed"):
        restore_backup(pg, folder, target)
    assert pg.query("SELECT value FROM sentinel;", target) == 123
    archive = folder / "database.dump"
    with archive.open("ab") as stream:
        stream.write(b"corrupted")
    with pytest.raises(BackupError, match="corrupt"):
        restore_backup(pg, folder, target)
    with Database(settings).transaction() as conn:
        conn.execute(
            "UPDATE schema_migrations SET checksum='changed' "
            "WHERE name=(SELECT min(name) FROM schema_migrations)"
        )
    with pytest.raises(BackupError, match="migrations"):
        create_backup(pg, tmp_path / "mismatch")
    with pytest.raises(RuntimeError, match="Applied migration changed"):
        migrate(Database(settings))
    with client(settings) as http:
        assert http.get("/health/ready").status_code == 503
        assert http.get("/health/live").status_code == 200
    assert pg.query("SELECT count(*) FROM schema_migrations;") == len(migration_checksums())


@pytest.mark.integration
def test_failed_archive_is_atomic_and_working_database_untouched(
    backup_lab: tuple[Postgres, Settings, str],
    tmp_path: Path,
) -> None:
    pg, _, target = backup_lab
    directory = tmp_path / "backup"
    manifest = create_backup(pg, directory)
    archive = directory / "database.dump"
    # Simulate a bad but checksummed archive; checksums detect corruption, not provenance.
    data = archive.read_bytes()[:100]
    archive.write_bytes(data)
    manifest.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BackupError, match="pg_restore failed"):
        restore_backup(pg, directory, target)
    assert pg.query("SELECT count(*) FROM pg_tables WHERE schemaname='public';", target) == 0
    assert pg.query("SELECT count(*) FROM schema_migrations;") == len(migration_checksums())


@pytest.mark.integration
def test_failed_upgrade_rolls_back_and_newer_database_rejects_old_release(
    backup_lab: tuple[Postgres, Settings, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pg, settings, _ = backup_lab
    package = tmp_path / "candidate"
    candidates = package / "migrations"
    candidates.mkdir(parents=True)
    for resource in files("marketob_api").joinpath("migrations").iterdir():
        if resource.name.endswith(".sql"):
            (candidates / resource.name).write_text(
                resource.read_text(encoding="utf-8"), encoding="utf-8"
            )
    (candidates / "011_failed.sql").write_text(
        "CREATE TABLE incomplete_upgrade(value integer); SELECT 1/0;", encoding="utf-8"
    )
    with monkeypatch.context() as patch:
        patch.setattr(import_module("marketob_api.migrate"), "files", lambda _: package)
        with pytest.raises(psycopg.errors.DivisionByZero):
            migrate(Database(settings))
    assert pg.query("SELECT count(*) FROM pg_tables WHERE tablename='incomplete_upgrade';") == 0
    assert migrate(Database(settings)) == []
    with client(settings) as http:
        assert http.get("/health/ready").status_code == 200
    pg.query("INSERT INTO schema_migrations(name,checksum) VALUES('999_future.sql','future');")
    with pytest.raises(RuntimeError, match="newer than this release"):
        migrate(Database(settings))
    with client(settings) as http:
        assert http.get("/health/ready").status_code == 503
