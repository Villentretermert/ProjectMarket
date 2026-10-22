"""Shared access policy used inside the same transaction as each resource operation."""

from typing import Any

from marketob_api.database import Connection
from marketob_api.errors import ApiError
from marketob_api.workspace_access import EDITORS, workspace


def require_owner(
    connection: Connection,
    channel_id: str,
    user_id: str,
    *,
    include_deleted: bool = False,
    roles: tuple[str, ...] = EDITORS,
) -> dict[str, Any]:
    candidate = connection.execute(
        "SELECT org_id FROM channel_access WHERE channel_id=%s", (channel_id,)
    ).fetchone()
    if candidate is None:
        raise ApiError(404, "object_not_found", "The requested object is unavailable.")
    organization = workspace(connection, candidate["org_id"], user_id, roles)
    row = connection.execute(
        "SELECT * FROM channel_access WHERE channel_id=%s AND org_id=%s "
        "AND (%s OR deleted_at IS NULL) FOR UPDATE",
        (channel_id, organization["org_id"], include_deleted),
    ).fetchone()
    if row is None:
        raise ApiError(404, "object_not_found", "The requested object is unavailable.")
    return {**row, "role": organization["role"]}


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
                    "SELECT 1 FROM memberships WHERE org_id=%s AND user_id=%s",
                    (row["org_id"], user_id),
                ).fetchone()
                is not None
            )
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
