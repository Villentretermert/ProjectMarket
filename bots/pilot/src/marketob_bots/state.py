"""Bot-owned SQLite journal: commit retry identities and inbox before network effects."""

import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from marketob_sdk import BotClient, BotEvent, ProtocolError


class StateError(Exception):
    """Restore the bot's journal instead of guessing whether an effect happened."""


def encode(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


class Journal:
    def __init__(self, path: Path, bot_id: str, channel_id: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS identity(bot_id TEXT NOT NULL,channel_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbound(resource_id TEXT PRIMARY KEY,
                revision INTEGER NOT NULL,
                content_hash TEXT NOT NULL,pending TEXT);
            CREATE TABLE IF NOT EXISTS inbox(action_request_id TEXT PRIMARY KEY,
                event_id TEXT UNIQUE NOT NULL,
                event TEXT NOT NULL,result TEXT,reported INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS demo_effects(action_request_id TEXT PRIMARY KEY,
                result TEXT NOT NULL,created_at TEXT NOT NULL);
        """)
        try:
            with self.db:
                self.db.execute("BEGIN IMMEDIATE")
                identity = self.db.execute("SELECT * FROM identity").fetchone()
                if identity is None:
                    self.db.execute("INSERT INTO identity VALUES (?,?)", (bot_id, channel_id))
                elif (identity["bot_id"], identity["channel_id"]) != (bot_id, channel_id):
                    raise StateError(
                        "This journal belongs to another bot/channel; "
                        "use its original configuration."
                    )
        except Exception:
            self.db.close()
            raise
        self.channel_id = channel_id

    def close(self) -> None:
        self.db.close()

    def flush_pending(self, client: BotClient) -> None:
        for row in self.db.execute(
            "SELECT resource_id,pending FROM outbound WHERE pending IS NOT NULL"
        ).fetchall():
            self._flush(client, row["resource_id"], json.loads(row["pending"]))

    def publish(
        self, client: BotClient, resource_id: str, kind: str, payload: dict[str, Any]
    ) -> None:
        existing = self.db.execute(
            "SELECT pending FROM outbound WHERE resource_id=?", (resource_id,)
        ).fetchone()
        if existing and existing["pending"]:
            self._flush(client, resource_id, json.loads(existing["pending"]))
        content_hash = hashlib.sha256(encode([kind, payload]).encode()).hexdigest()
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            old = self.db.execute(
                "SELECT * FROM outbound WHERE resource_id=?", (resource_id,)
            ).fetchone()
            if old and old["pending"]:
                raise StateError(
                    "Another publisher is active for this journal; run one process per bot."
                )
            if old and old["content_hash"] == content_hash:
                return
            revision = old["revision"] + 1 if old else 1
            body = {
                "schema_version": "1.0",
                "message_id": "msg_" + uuid4().hex,
                "channel_id": self.channel_id,
                "resource_id": resource_id,
                "source_revision": revision,
                "occurred_at": datetime.now(UTC).isoformat(),
                "kind": "data",
                "content_type": kind,
                "payload": payload,
            }
            self.db.execute(
                "INSERT INTO outbound VALUES (?,?,?,?) ON CONFLICT(resource_id) DO UPDATE SET "
                "revision=excluded.revision,content_hash=excluded.content_hash,pending=excluded.pending",
                (resource_id, revision, content_hash, encode(body)),
            )
        self._flush(client, resource_id, body)

    def _flush(self, client: BotClient, resource_id: str, body: dict[str, Any]) -> None:
        receipt = client.send_message(body)
        if receipt["message_id"] != body["message_id"]:
            raise ProtocolError("Receipt does not match the pending message.")
        with self.db:
            self.db.execute(
                "UPDATE outbound SET pending=NULL WHERE resource_id=? AND pending=?",
                (resource_id, encode(body)),
            )

    def remember(self, event: BotEvent) -> None:
        if event["channel_id"] != self.channel_id:
            raise StateError("This example processes only its configured channel.")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            old = self.db.execute(
                "SELECT event FROM inbox WHERE action_request_id=?", (event["action_request_id"],)
            ).fetchone()
            if old and old["event"] != encode(event):
                raise ProtocolError("A stable event identity changed its body.")
            self.db.execute(
                "INSERT INTO inbox(action_request_id,event_id,event) VALUES (?,?,?) "
                "ON CONFLICT(action_request_id) DO NOTHING",
                (event["action_request_id"], event["event_id"], encode(event)),
            )

    def pending(self) -> list[BotEvent]:
        return [
            json.loads(row["event"])
            for row in self.db.execute(
                "SELECT event FROM inbox WHERE reported=0 ORDER BY rowid LIMIT 100"
            )
        ]

    def finish(self, request_id: str) -> None:
        with self.db:
            self.db.execute("UPDATE inbox SET reported=1 WHERE action_request_id=?", (request_id,))

    def demo_result(self, event: BotEvent, accepted: bool) -> dict[str, Any]:
        # This ledger is the demo effect. A real service needs its own idempotency/status API.
        request_id = event["action_request_id"]
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute(
                "SELECT result FROM demo_effects WHERE action_request_id=?", (request_id,)
            ).fetchone()
            if row:
                return dict(json.loads(row["result"]))
            result = {
                "result_id": "result_" + hashlib.sha256(request_id.encode()).hexdigest()[:32],
                "result_revision": 1,
                "state": "confirmed" if accepted else "failed",
                "summary": "Demo request confirmed. No payment has been taken."
                if accepted
                else "Demo supplier declined this request. No payment has been taken.",
                "external_reference": "demo_" + request_id,
            }
            self.db.execute(
                "INSERT INTO demo_effects VALUES (?,?,?)",
                (request_id, encode(result), datetime.now(UTC).isoformat()),
            )
            self.db.execute(
                "UPDATE inbox SET result=? WHERE action_request_id=?", (encode(result), request_id)
            )
            return result
