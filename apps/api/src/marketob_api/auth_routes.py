"""Local identity endpoints; every successful mutation commits before responding."""

import time
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, Response
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from marketob_api.access import require_owner
from marketob_api.config import Settings
from marketob_api.cursors import Scan, decode_scan, encode_scan, session_binding
from marketob_api.database import Database
from marketob_api.errors import ApiError
from marketob_api.identity import (
    COOKIE,
    HASHER,
    authenticate,
    digest,
    identifier,
    new_session,
    rate_limit,
    request_origin,
    require_business,
    verify_password,
)
from marketob_api.request_state import reconcile_access, reconcile_user
from marketob_api.workspace_access import MANAGERS


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class Credentials(ClosedModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9_-]+$")
    password: SecretStr = Field(min_length=12, max_length=128)


class RegisterUser(Credentials):
    display_name: str = Field(min_length=1, max_length=80)


class BusinessProfile(ClosedModel):
    name: str = Field(min_length=1, max_length=80)


class ConfirmPassword(ClosedModel):
    password: SecretStr = Field(min_length=12, max_length=128)


class Empty(ClosedModel):
    pass


def router(settings: Settings) -> APIRouter:
    api = APIRouter(prefix="/v1", tags=["identity"])
    database = Database(settings)

    def auth_attempt(request: Request) -> str:
        origin = request_origin(request, settings, unsafe=True)
        peer = request.client.host if request.client else "unknown"
        rate_limit(database, "auth:" + digest(peer), settings.auth_rate_limit)
        return origin

    @api.post("/auth/register", status_code=201)
    def register(body: RegisterUser, request: Request, response: Response) -> dict[str, Any]:
        origin = auth_attempt(request)
        password_hash = HASHER.hash(body.password.get_secret_value())
        try:
            with database.transaction() as connection:
                user_id = identifier("usr")
                connection.execute(
                    "INSERT INTO users(user_id,username,display_name,password_hash) "
                    "VALUES (%s,%s,%s,%s)",
                    (user_id, body.username, body.display_name, password_hash),
                )
                session = new_session(connection, user_id, origin, settings, response)
        except UniqueViolation:
            raise ApiError(409, "username_unavailable", "This username is unavailable.") from None
        return session.session_payload()

    @api.post("/auth/login")
    def login(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
        origin = auth_attempt(request)
        with database.transaction() as connection:
            row = connection.execute(
                "SELECT user_id,password_hash FROM users WHERE username=%s AND deleted_at IS NULL "
                "FOR UPDATE",
                (body.username,),
            ).fetchone()
            encoded = row["password_hash"] if row else None
            if not verify_password(encoded, body.password.get_secret_value()):
                raise ApiError(401, "invalid_credentials", "Username or password is incorrect.")
            assert row is not None
            assert isinstance(encoded, str)
            if HASHER.check_needs_rehash(encoded):
                connection.execute(
                    "UPDATE users SET password_hash=%s WHERE user_id=%s",
                    (HASHER.hash(body.password.get_secret_value()), row["user_id"]),
                )
            session = new_session(connection, row["user_id"], origin, settings, response)
        return session.session_payload()

    @api.get("/auth/session")
    def session(request: Request) -> dict[str, Any]:
        with database.transaction() as connection:
            return authenticate(connection, request, settings).session_payload()

    @api.delete("/auth/session", status_code=204)
    def logout(request: Request, response: Response) -> None:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            connection.execute("DELETE FROM sessions WHERE token_hash=%s", (digest(current.token),))
        response.delete_cookie(
            COOKIE,
            path="/",
            httponly=True,
            secure=current.origin.startswith("https://"),
            samesite="strict",
        )

    @api.put("/account/business-profile")
    def business_profile(body: BusinessProfile, request: Request) -> dict[str, str]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            row = connection.execute(
                "INSERT INTO organizations(org_id,owner_user_id,name) VALUES (%s,%s,%s) "
                "ON CONFLICT (owner_user_id) DO UPDATE SET name=EXCLUDED.name "
                "RETURNING org_id,name",
                (identifier("org"), current.user_id, body.name),
            ).fetchone()
            assert row is not None
            connection.execute(
                "INSERT INTO memberships(org_id,user_id,role) VALUES (%s,%s,'owner') "
                "ON CONFLICT DO NOTHING",
                (row["org_id"], current.user_id),
            )
            return {"org_id": row["org_id"], "name": row["name"], "role": "owner"}

    @api.get("/account/business-profile")
    def get_business_profile(request: Request) -> dict[str, str]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            row = connection.execute(
                "SELECT org_id,name FROM organizations WHERE owner_user_id=%s AND active",
                (current.user_id,),
            ).fetchone()
            if row is None:
                raise ApiError(404, "object_not_found", "Create your business profile first.")
            return {"org_id": row["org_id"], "name": row["name"], "role": "owner"}

    @api.delete("/account", status_code=204)
    def delete_account(body: ConfirmPassword, request: Request, response: Response) -> None:
        auth_attempt(request)
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            row = connection.execute(
                "SELECT password_hash FROM users WHERE user_id=%s FOR NO KEY UPDATE",
                (current.user_id,),
            ).fetchone()
            assert row is not None
            if not verify_password(row["password_hash"], body.password.get_secret_value()):
                raise ApiError(401, "invalid_credentials", "Password verification failed.")
            connection.execute(
                "SELECT org_id FROM organizations WHERE owner_user_id=%s FOR NO KEY UPDATE",
                (current.user_id,),
            )
            connection.execute("DELETE FROM sessions WHERE user_id=%s", (current.user_id,))
            connection.execute(
                "INSERT INTO change_outbox(channel_id,user_id,kind) "
                "SELECT channel_id,%s,'access.revoked' FROM grants WHERE user_id=%s",
                (current.user_id, current.user_id),
            )
            connection.execute("DELETE FROM grants WHERE user_id=%s", (current.user_id,))
            connection.execute(
                "INSERT INTO change_outbox(channel_id,kind) SELECT a.channel_id,'source.deleted' "
                "FROM channel_access a JOIN organizations o USING(org_id) WHERE o.owner_user_id=%s",
                (current.user_id,),
            )
            connection.execute(
                "UPDATE channel_access SET deleted_at=now(),published=false WHERE org_id IN "
                "(SELECT org_id FROM organizations WHERE owner_user_id=%s)",
                (current.user_id,),
            )
            connection.execute(
                "UPDATE organizations SET active=false WHERE owner_user_id=%s",
                (current.user_id,),
            )
            connection.execute("DELETE FROM memberships WHERE user_id=%s", (current.user_id,))
            connection.execute(
                "UPDATE users SET deleted_at=now(),display_name='Deleted user',password_hash=NULL "
                "WHERE user_id=%s",
                (current.user_id,),
            )
            owned = connection.execute(
                "SELECT channel_id FROM channel_access WHERE org_id IN "
                "(SELECT org_id FROM organizations WHERE owner_user_id=%s)",
                (current.user_id,),
            ).fetchall()
            for source in owned:
                reconcile_access(connection, source["channel_id"], disabled=True)
            reconcile_user(connection, current.user_id)
        response.delete_cookie(
            COOKIE,
            path="/",
            httponly=True,
            secure=current.origin.startswith("https://"),
            samesite="strict",
        )

    @api.get("/users/by-username/{username}")
    def lookup_user(username: str, request: Request) -> dict[str, str]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            require_business(connection, current.user_id, request.headers.get("x-workspace-id"))
            row = connection.execute(
                "SELECT user_id,username,display_name FROM users "
                "WHERE username=%s AND deleted_at IS NULL",
                (username,),
            ).fetchone()
            if row is None:
                raise ApiError(404, "object_not_found", "The registered user is unavailable.")
            return {key: str(row[key]) for key in ("user_id", "username", "display_name")}

    @api.put("/owner/channels/{channel_id}/grants/{user_id}", status_code=204)
    def grant(channel_id: str, user_id: str, body: Empty, request: Request) -> None:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            # Deactivation locks the target user before their pending request channels.
            # Check the user first so granting does not invert that lock order.
            user = connection.execute(
                "SELECT 1 FROM users WHERE user_id=%s AND deleted_at IS NULL FOR SHARE",
                (user_id,),
            ).fetchone()
            require_owner(connection, channel_id, current.user_id, roles=MANAGERS)
            if user is None:
                raise ApiError(404, "object_not_found", "The registered user is unavailable.")
            connection.execute(
                "INSERT INTO grants(channel_id,user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (channel_id, user_id),
            )
            connection.execute(
                "INSERT INTO change_outbox(channel_id,user_id,kind) "
                "VALUES (%s,%s,'channel.changed')",
                (channel_id, user_id),
            )

    @api.delete("/owner/channels/{channel_id}/grants/{user_id}", status_code=204)
    def revoke_grant(channel_id: str, user_id: str, request: Request) -> None:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            require_owner(connection, channel_id, current.user_id, roles=MANAGERS)
            removed = connection.execute(
                "DELETE FROM grants WHERE channel_id=%s AND user_id=%s RETURNING user_id",
                (channel_id, user_id),
            ).fetchone()
            if removed:
                reconcile_access(connection, channel_id)
                connection.execute(
                    "INSERT INTO change_outbox(channel_id,user_id,kind) "
                    "VALUES (%s,%s,'access.revoked')",
                    (channel_id, user_id),
                )

    @api.get("/owner/channels/{channel_id}/audience")
    @api.get("/owner/channels/{channel_id}/grants")
    def list_grants(
        channel_id: str,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
    ) -> dict[str, Any]:
        with database.transaction() as connection:
            current = authenticate(connection, request, settings)
            require_owner(connection, channel_id, current.user_id, roles=MANAGERS)
            profiles = request.url.path.endswith("/audience")
            binding = session_binding(
                current.token, ("audience:" if profiles else "grants:") + channel_id
            )
            if cursor:
                scan = decode_scan(connection, binding, cursor)
            else:
                maximum = connection.execute(
                    "SELECT coalesce(max(sequence),0) AS upper FROM grants WHERE channel_id=%s",
                    (channel_id,),
                ).fetchone()
                assert maximum is not None
                scan = Scan(maximum["upper"], 0, int(time.time()) + 60)
            rows = connection.execute(
                "SELECT sequence,user_id FROM grants WHERE channel_id=%s AND sequence>%s "
                "AND sequence<=%s ORDER BY sequence LIMIT %s",
                (channel_id, scan.after, scan.upper, limit + 1),
            ).fetchall()
            next_cursor = None
            if len(rows) > limit:
                next_cursor = encode_scan(
                    connection, binding, Scan(scan.upper, rows[limit - 1]["sequence"], scan.expires)
                )
            items = []
            for row in rows[:limit]:
                if profiles:
                    user = connection.execute(
                        "SELECT user_id,username,display_name FROM users WHERE user_id=%s "
                        "AND deleted_at IS NULL",
                        (row["user_id"],),
                    ).fetchone()
                    if user:
                        items.append(user)
                else:
                    items.append({"user_id": row["user_id"]})
            return {
                "items": items,
                "next_cursor": next_cursor,
            }

    return api
