"""Opaque sessions and personal business ownership; client roles are never trusted."""

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Request, Response

from marketob_api.config import Settings
from marketob_api.database import Connection, Database
from marketob_api.errors import ApiError

HASHER = PasswordHasher()
# Nonexistent accounts still pay the password verification cost.
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))
COOKIE = "marketob_session"


def identifier(prefix: str) -> str:
    return prefix + "_" + uuid4().hex


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(encoded: str | None, password: str) -> bool:
    try:
        valid = HASHER.verify(encoded or DUMMY_HASH, password)
        return bool(encoded) and valid
    except VerificationError, InvalidHashError:
        return False


def csrf_for(token: str) -> str:
    raw = hmac.digest(token.encode(), b"marketob-csrf-v1", "sha256")
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def request_origin(request: Request, settings: Settings, *, unsafe: bool) -> str:
    origin = request.headers.get("origin")
    if origin is None and not unsafe:
        origin = str(request.base_url).rstrip("/")
    if origin not in settings.allowed_origins:
        raise ApiError(403, "csrf_failed", "Use an explicitly allowed application origin.")
    assert origin is not None
    return origin


@dataclass(frozen=True)
class Identity:
    user_id: str
    username: str
    display_name: str
    expires_at: datetime
    origin: str
    token: str = field(repr=False)

    def session_payload(self) -> dict[str, Any]:
        return {
            "user": {
                "user_id": self.user_id,
                "username": self.username,
                "display_name": self.display_name,
            },
            "csrf_token": csrf_for(self.token),
            "expires_at": self.expires_at.astimezone(UTC),
        }


def authenticate(connection: Connection, request: Request, settings: Settings) -> Identity:
    token = request.cookies.get(COOKIE, "")
    if not re.fullmatch(r"ms_[A-Za-z0-9_-]{43}", token):
        raise ApiError(401, "invalid_credentials", "Sign in to continue.")
    unsafe = request.method not in {"GET", "HEAD", "OPTIONS"}
    origin = request_origin(request, settings, unsafe=unsafe)
    row = connection.execute(
        "SELECT u.user_id, u.username, u.display_name, s.expires_at, s.origin "
        "FROM sessions s JOIN users u USING(user_id) "
        "WHERE s.token_hash=%s AND s.expires_at>now() AND u.deleted_at IS NULL "
        "FOR SHARE OF s, u",
        (digest(token),),
    ).fetchone()
    if row is None or row["origin"] != origin:
        raise ApiError(401, "invalid_credentials", "Sign in to continue.")
    if unsafe and not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf_for(token)):
        raise ApiError(403, "csrf_failed", "The session verification token is invalid.")
    bucket = "user-write:" + str(row["user_id"]) if unsafe else "session-read:" + digest(token)
    rate_limit(
        Database(settings),
        bucket,
        settings.write_rate_limit if unsafe else settings.read_rate_limit,
    )
    return Identity(**row, token=token)


def new_session(
    connection: Connection, user_id: str, origin: str, settings: Settings, response: Response
) -> Identity:
    token = "ms_" + secrets.token_urlsafe(32)
    row = connection.execute(
        "INSERT INTO sessions(token_hash,user_id,origin,expires_at) "
        "VALUES (%s,%s,%s,now()+make_interval(hours => %s)) RETURNING expires_at",
        (digest(token), user_id, origin, settings.session_hours),
    ).fetchone()
    assert row is not None
    user = connection.execute(
        "SELECT user_id,username,display_name FROM users WHERE user_id=%s", (user_id,)
    ).fetchone()
    assert user is not None
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=origin.startswith("https://"),
        samesite="strict",
        path="/",
    )
    return Identity(**user, expires_at=row["expires_at"], origin=origin, token=token)


def require_business(connection: Connection, user_id: str) -> str:
    row = connection.execute(
        "SELECT o.org_id FROM organizations o JOIN memberships m USING(org_id) "
        "WHERE o.owner_user_id=%s AND m.user_id=%s AND m.role='owner' AND o.active "
        "FOR SHARE OF o, m",
        (user_id, user_id),
    ).fetchone()
    if row is None:
        raise ApiError(403, "insufficient_scope", "Create your business profile first.")
    return str(row["org_id"])


def rate_limit(database: Database, bucket: str, limit: int) -> None:
    # Commit attempts independently, including failed login/registration requests.
    with database.transaction() as connection:
        row = connection.execute(
            "INSERT INTO rate_windows(bucket,window_start,hits) "
            "VALUES (%s,date_trunc('minute',now()),1) ON CONFLICT (bucket) DO UPDATE "
            "SET window_start=date_trunc('minute',now()), hits=CASE "
            "WHEN rate_windows.window_start=date_trunc('minute',now()) "
            "THEN rate_windows.hits+1 ELSE 1 END RETURNING hits, "
            "GREATEST(1,ceil(extract(epoch FROM "
            "(window_start+interval '1 minute'-now())))) AS retry",
            (bucket,),
        ).fetchone()
    assert row is not None
    if row["hits"] > limit:
        raise ApiError(
            429, "rate_limited", "Too many requests. Try again later.", int(row["retry"])
        )
