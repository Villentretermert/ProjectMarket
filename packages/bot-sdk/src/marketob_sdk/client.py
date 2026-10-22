"""Bounded JSON, explicit TLS policy and retry identities preserved byte-for-byte."""

import json
import random
import re
import time
from http.client import HTTPException
from importlib.resources import files
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from marketob_sdk.types import ActionRequest, EventPage, Receipt

SCHEMAS = json.loads(files("contracts").joinpath("schemas.json").read_text(encoding="utf-8"))[
    "$defs"
]
SAFE_CODES = set(
    "invalid_credentials insufficient_scope source_unavailable request_not_found "
    "object_not_found request_cancelled ack_required terminal_conflict stale_result_revision "
    "idempotency_conflict stale_source_revision rate_limited storage_unavailable "
    "invalid_cursor cursor_expired invalid_query invalid_request invalid_json "
    "unsupported_schema_version payload_too_large unsupported_currency invalid_text "
    "duplicate_series invalid_chart_order unsupported_encoding unsupported_media_type "
    "internal_error".split()
)


class APIError(Exception):
    def __init__(self, status: int, code: str, retry_after: int | None = None):
        self.status = status
        self.code = code if code in SAFE_CODES else "api_error"
        self.retry_after = retry_after
        super().__init__(f"MarkeTOB HTTP {status}: {self.code}")


class TransportError(Exception):
    """Outcome may be ambiguous; recover with the same durable request identity."""


class ProtocolError(ValueError):
    """Local request or remote response does not satisfy the bounded contract."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        # Never forward an operational credential to a redirect target.
        return None


def validate(name: str, value: Any) -> None:
    validator = Draft202012Validator(
        {"$defs": SCHEMAS, "$ref": "#/$defs/" + name}, format_checker=FormatChecker()
    )
    if next(validator.iter_errors(value), None) is not None:
        raise ProtocolError("Payload does not match " + name)


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise ProtocolError("Use a valid opaque identifier.")
    return value


def invalid_constant(value: str) -> None:
    raise ValueError("Non-finite JSON is unsupported")


class BotClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        attempts: int = 4,
        timeout: float = 35,
        allow_container_http: bool = False,
    ):
        try:
            url = urlsplit(base_url)
            permitted_http = url.hostname in {"localhost", "127.0.0.1", "::1"} or (
                allow_container_http and url.hostname == "api"
            )
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username is not None
                or url.password is not None
                or url.query
                or url.fragment
                or url.path not in {"", "/"}
                or (url.scheme == "http" and not permitted_http)
                or url.port == 0
            ):
                raise ValueError
        except ValueError:
            raise ProtocolError(
                "Use an HTTPS API origin or a loopback development origin."
            ) from None
        if api_key is not None and not re.fullmatch(r"mb_[A-Za-z0-9_-]{43}", api_key):
            raise ProtocolError(
                "Use an operational bot key, not a registration or user credential."
            )
        if not 1 <= attempts <= 6 or not 26 <= timeout <= 120:
            raise ProtocolError("Use 1..6 attempts and a 26..120 second timeout.")
        self.base_url = base_url.rstrip("/")
        self._key = api_key
        self.attempts, self.timeout = attempts, timeout
        self._opener = build_opener(NoRedirect())

    def __repr__(self) -> str:
        return "BotClient(credentials=<redacted>)"

    def _request(
        self,
        method: str,
        path: str,
        schema: str,
        body: dict[str, Any] | None = None,
        *,
        credential: str | None = None,
        retry: bool = True,
        expected: int = 200,
    ) -> Any:
        key = credential or self._key
        if key is None:
            raise ProtocolError("An operational key is required for this call.")
        try:
            raw = (
                json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
                    "utf-8"
                )
                if body is not None
                else None
            )
        except ValueError, UnicodeError, RecursionError:
            raise ProtocolError("Use bounded valid UTF-8 JSON.") from None
        if raw is not None and len(raw) > 262144:
            raise ProtocolError("Request exceeds 256 KiB.")
        attempts = self.attempts if retry else 1
        for attempt in range(attempts):
            retry_after = None
            try:
                request = Request(
                    self.base_url + path,
                    method=method,
                    data=raw,
                    headers={
                        "Authorization": "Bearer " + key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "User-Agent": "MarkeTOB-Bot-SDK/0.1",
                    },
                )
                try:
                    response = self._opener.open(request, timeout=self.timeout)
                except HTTPError as error:
                    response = error
                with response:
                    status = response.status
                    data = response.read(524289)
                    header = response.headers.get("Retry-After", "")
                    if header.isdecimal() and len(header) <= 8:
                        retry_after = int(header)
                if len(data) > 524288:
                    raise ProtocolError("Response exceeds 512 KiB.")
                try:
                    value = json.loads(data.decode("utf-8"), parse_constant=invalid_constant)
                except ValueError, UnicodeError, RecursionError:
                    if status == expected:
                        raise ProtocolError("Response is not valid JSON.") from None
                    value = {}
                if status == expected:
                    validate(schema, value)
                    return value
                code = value.get("code", "api_error") if isinstance(value, dict) else "api_error"
                failure = APIError(
                    status, code if isinstance(code, str) else "api_error", retry_after
                )
                if status not in {429, 503} or attempt == attempts - 1 or (retry_after or 0) > 60:
                    raise failure
            except URLError, TimeoutError, OSError, HTTPException:
                if attempt == attempts - 1:
                    raise TransportError(
                        "API transport failed; retry the same durable identity."
                    ) from None
            time.sleep(max(min(2**attempt, 30), retry_after or 0) + random.uniform(0, 0.25))
        raise AssertionError("Retry loop must return or raise")

    def exchange_registration(self, credential: str) -> dict[str, Any]:
        if not re.fullmatch(r"mr_[A-Za-z0-9_-]{43}", credential):
            raise ProtocolError("Use a one-time registration credential.")
        # A lost exchange response is recovered by the owner issuing a new key.
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/v1/bot-registrations/exchange",
                "KeySecret",
                {},
                credential=credential,
                retry=False,
                expected=201,
            ),
        )

    def identity(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", "/v1/bot/identity", "BotIdentity"))

    def send_message(self, body: dict[str, Any]) -> Receipt:
        validate("Message", body)
        return cast(Receipt, self._request("POST", "/v1/bot/messages", "Receipt", body))

    def events(self, *, cursor: str | None = None, limit: int = 100, wait: int = 0) -> EventPage:
        if not 1 <= limit <= 100 or not 0 <= wait <= 25 or (cursor and wait):
            raise ProtocolError("Use limit 1..100; wait 0..25 only on the first page.")
        query = {"limit": str(limit), "wait": str(wait), **({"cursor": cursor} if cursor else {})}
        return cast(
            EventPage, self._request("GET", "/v1/bot/events?" + urlencode(query), "EventPage")
        )

    def requests(self, *, cursor: str | None = None, limit: int = 100) -> EventPage:
        if not 1 <= limit <= 100:
            raise ProtocolError("Use limit 1..100.")
        query = {"limit": str(limit), **({"cursor": cursor} if cursor else {})}
        return cast(
            EventPage, self._request("GET", "/v1/bot/requests?" + urlencode(query), "BotEventList")
        )

    def ack(self, event_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("POST", "/v1/bot/events/" + identifier(event_id) + "/ack", "Ack", {}),
        )

    def result(self, event_id: str, body: dict[str, Any]) -> ActionRequest:
        validate("Result", body)
        return cast(
            ActionRequest,
            self._request(
                "POST", "/v1/bot/events/" + identifier(event_id) + "/result", "ActionRequest", body
            ),
        )
