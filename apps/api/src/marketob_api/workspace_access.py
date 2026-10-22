"""Workspace roles are resolved on every operation under the organization lock."""

from typing import Any

from marketob_api.database import Connection
from marketob_api.errors import ApiError

EDITORS = ("owner", "admin", "editor")
MANAGERS = ("owner", "admin")


def workspace(
    connection: Connection,
    org_id: str,
    user_id: str,
    roles: tuple[str, ...] = EDITORS,
    *,
    exclusive: bool = False,
) -> dict[str, Any]:
    # Team changes take UPDATE; all authorized work holds SHARE until commit.
    lock = "FOR UPDATE" if exclusive else "FOR SHARE"
    org = connection.execute(
        "SELECT * FROM organizations WHERE org_id=%s AND active " + lock, (org_id,)
    ).fetchone()
    if org is None:
        raise ApiError(404, "object_not_found", "The workspace is unavailable.")
    member = connection.execute(
        "SELECT role FROM memberships WHERE org_id=%s AND user_id=%s", (org_id, user_id)
    ).fetchone()
    if member is None:
        raise ApiError(404, "object_not_found", "The workspace is unavailable.")
    if member["role"] not in roles:
        raise ApiError(
            403, "insufficient_scope", "Your workspace role does not allow this operation."
        )
    return {**org, "role": member["role"]}


def audience_guard(access: dict[str, Any], visibility: str, previous: str) -> None:
    if access["role"] == "editor" and visibility != previous:
        raise ApiError(403, "insufficient_scope", "Only Owner or Admin can change the audience.")
