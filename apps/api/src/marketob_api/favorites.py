"""Account-synced references, manual order and observed revision markers."""

from typing import Any

from fastapi import APIRouter, Request

from marketob_api.access import require_read
from marketob_api.auth_routes import Empty
from marketob_api.channels import content, published_definition
from marketob_api.config import Settings
from marketob_api.database import Connection, Database
from marketob_api.errors import ApiError
from marketob_api.identity import authenticate
from marketob_api.payloads import validate_payload


def lock_state(connection: Connection, user_id: str) -> int:
    # Serialize only this collection, without upgrading authenticate's user share lock.
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("favorites:" + user_id,)
    )
    connection.execute(
        "INSERT INTO favorite_state(user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,)
    )
    row = connection.execute(
        "SELECT revision FROM favorite_state WHERE user_id=%s", (user_id,)
    ).fetchone()
    assert row is not None
    return int(row["revision"])


def bump(connection: Connection, user_id: str) -> None:
    connection.execute("UPDATE favorite_state SET revision=revision+1 WHERE user_id=%s", (user_id,))


def listing(connection: Connection, user_id: str, revision: int) -> dict[str, Any]:
    rows = connection.execute(
        "SELECT * FROM favorites WHERE user_id=%s ORDER BY channel_id", (user_id,)
    ).fetchall()
    items = []
    for saved in rows:
        item: dict[str, Any] = {"channel_id": saved["channel_id"], "available": False}
        try:
            require_read(connection, saved["channel_id"], user_id)
            row = content(connection, saved["channel_id"])
            value = published_definition(connection, row)
            item.update(
                available=True,
                title=value["title"],
                slug=row["slug"],
                unread=(
                    row["data_revision"] > saved["seen_data"]
                    or row["published_version"] > saved["seen_template"]
                ),
            )
        except ApiError as error:
            if error.status != 404:
                raise
        items.append((saved["position"], item))
    return {"revision": revision, "items": [item for _, item in sorted(items, key=lambda x: x[0])]}


def router(settings: Settings) -> APIRouter:
    api = APIRouter(prefix="/v1/favorites", tags=["favorites"])
    database = Database(settings)

    @api.get("")
    def read(request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            revision = lock_state(connection, current.user_id)
            return listing(connection, current.user_id, revision)

    @api.put("/order")
    def order(body: dict[str, Any], request: Request) -> dict[str, int]:
        validate_payload("FavoriteOrder", body)
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            revision = lock_state(connection, current.user_id)
            rows = connection.execute(
                "SELECT channel_id FROM favorites WHERE user_id=%s ORDER BY position",
                (current.user_id,),
            ).fetchall()
            before = [r["channel_id"] for r in rows]
            if body["expected_revision"] != revision or set(before) != set(body["channel_ids"]):
                raise ApiError(
                    409, "favorites_conflict", "Favorites changed. Refresh before reordering."
                )
            if before != body["channel_ids"]:
                for position, channel_id in enumerate(body["channel_ids"]):
                    connection.execute(
                        "UPDATE favorites SET position=%s WHERE user_id=%s AND channel_id=%s",
                        (position, current.user_id, channel_id),
                    )
                bump(connection, current.user_id)
                revision += 1
            return {"revision": revision}

    @api.put("/{channel_id}", status_code=204)
    def save(channel_id: str, body: Empty, request: Request) -> None:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            lock_state(connection, current.user_id)
            require_read(connection, channel_id, current.user_id)
            rows = connection.execute(
                "SELECT channel_id,position FROM favorites WHERE user_id=%s", (current.user_id,)
            ).fetchall()
            if channel_id in {row["channel_id"] for row in rows}:
                return
            if len(rows) >= 100:
                raise ApiError(409, "favorites_limit", "The pilot supports up to 100 favorites.")
            connection.execute(
                "INSERT INTO favorites(user_id,channel_id,position) VALUES (%s,%s,%s)",
                (current.user_id, channel_id, max((r["position"] for r in rows), default=-1) + 1),
            )
            bump(connection, current.user_id)

    @api.delete("/{channel_id}", status_code=204)
    def remove(channel_id: str, request: Request) -> None:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            lock_state(connection, current.user_id)
            removed = connection.execute(
                "DELETE FROM favorites WHERE user_id=%s AND channel_id=%s RETURNING channel_id",
                (current.user_id, channel_id),
            ).fetchone()
            if removed:
                bump(connection, current.user_id)

    @api.put("/{channel_id}/seen", status_code=204)
    def seen(channel_id: str, body: dict[str, Any], request: Request) -> None:
        validate_payload("FavoriteSeen", body)
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            lock_state(connection, current.user_id)
            require_read(connection, channel_id, current.user_id)
            row = content(connection, channel_id)
            if (
                body["data_revision"] > row["data_revision"]
                or body["template_version"] > row["published_version"]
            ):
                raise ApiError(409, "revision_conflict", "Mark only revisions already observed.")
            connection.execute(
                "UPDATE favorites SET seen_data=greatest(seen_data,%s),"
                "seen_template=greatest(seen_template,%s) WHERE user_id=%s AND channel_id=%s",
                (body["data_revision"], body["template_version"], current.user_id, channel_id),
            )

    return api
