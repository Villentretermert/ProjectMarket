"""Short-lived, server-authenticated fixed scans bound to caller and operation."""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from marketob_api.database import Connection
from marketob_api.errors import ApiError


@dataclass(frozen=True)
class Scan:
    upper: int
    after: int
    expires: int


def signing_key(connection: Connection) -> bytes:
    row = connection.execute("SELECT secret FROM server_keys WHERE purpose='cursor'").fetchone()
    if row is None:
        raise ApiError(503, "storage_unavailable", "Apply database migrations first.")
    return bytes(row["secret"])


def encode_scan(connection: Connection, binding: str, scan: Scan) -> str:
    body = json.dumps(
        [binding, scan.upper, scan.after, scan.expires], separators=(",", ":")
    ).encode()
    signature = hmac.digest(signing_key(connection), body, "sha256")
    return base64.urlsafe_b64encode(signature + body).decode().rstrip("=")


def decode_scan(connection: Connection, binding: str, token: str) -> Scan:
    try:
        raw = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
        signature, body = raw[:32], raw[32:]
        expected = hmac.digest(signing_key(connection), body, "sha256")
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        actual_binding, upper, after, expires = json.loads(body)
        if (
            actual_binding != binding
            or any(type(value) is not int for value in (upper, after, expires))
            or not 0 <= after <= upper
        ):
            raise ValueError
    except ValueError, TypeError:
        raise ApiError(400, "invalid_cursor", "The scan cursor is invalid.") from None
    if expires <= time.time():
        raise ApiError(410, "cursor_expired", "Restart the scan without a cursor.")
    return Scan(upper, after, expires)


def session_binding(token: str, scope: str) -> str:
    return hashlib.sha256((token + ":" + scope).encode()).hexdigest()
