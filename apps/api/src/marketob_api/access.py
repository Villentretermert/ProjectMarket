"""Shared access policy used inside the same transaction as each resource operation."""

from typing import Any

from marketob_api.database import Connection
from marketob_api.errors import ApiError
from marketob_api.identity import require_business


def require_owner(
    connection: Connection, channel_id: str, user_id: str, *, include_deleted: bool = False
) -> dict[str, Any]:
    organization = require_business(connection, user_id)
    row = connection.execute(
        "SELECT * FROM channel_access WHERE channel_id=%s AND org_id=%s "
        "AND (%s OR deleted_at IS NULL) FOR UPDATE",
        (channel_id, organization, include_deleted),
    ).fetchone()
    if row is None:
        raise ApiError(404, "object_not_found", "The requested object is unavailable.")
    return row


def require_read(
    connection: Connection, channel_id: str, user_id: str | None, *, exclusive: bool = False
) -> dict[str, Any]:
    # Match bot/owner lock order: organization before channel. No lock upgrades for actions.
    organization = connection.execute(
        "SELECT o.org_id,o.owner_user_id FROM organizations o JOIN channel_access a USING(org_id) "
        "WHERE a.channel_id=%s AND o.active FOR SHARE OF o",
        (channel_id,),
    ).fetchone()
    if organization is None:
        raise ApiError(404, "source_unavailable", "This source is unavailable.")
    lock = "FOR UPDATE" if exclusive else "FOR SHARE"
    row = connection.execute(
        "SELECT * FROM channel_access WHERE channel_id=%s AND org_id=%s "
        "AND deleted_at IS NULL AND published " + lock,
        (channel_id, organization["org_id"]),
    ).fetchone()
    if row is not None:
        row["owner_user_id"] = organization["owner_user_id"]
        allowed = row["visibility"] == "public" or row["owner_user_id"] == user_id
        if not allowed and user_id is not None:
            allowed = (
                connection.execute(
                    "SELECT 1 FROM grants WHERE channel_id=%s AND user_id=%s",
                    (channel_id, user_id),
                ).fetchone()
                is not None
            )
        if allowed:
            return row
    raise ApiError(404, "source_unavailable", "This source is unavailable.")
