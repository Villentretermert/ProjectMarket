"""HTTP SDK contracts, stable retries, safe failures and real redirect rejection."""

import io
import json
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.error import URLError
from urllib.request import Request

import pytest
from marketob_sdk import APIError, BotClient, ProtocolError, TransportError

KEY = "mb_" + "a" * 43
MESSAGE: dict[str, Any] = {
    "schema_version": "1.0",
    "message_id": "msg_one",
    "channel_id": "ch_one",
    "resource_id": "news",
    "source_revision": 1,
    "occurred_at": "2026-10-22T00:00:00Z",
    "kind": "text",
    "payload": {"title": "Synthetic", "body": "SDK check"},
}
RECEIPT = {
    "message_id": "msg_one",
    "receipt_id": "receipt_one",
    "data_revision": 1,
    "received_at": "2026-10-22T00:00:00Z",
}


class Reply(io.BytesIO):
    def __init__(self, status: int, value: Any, headers: dict[str, str] | None = None):
        super().__init__(value if isinstance(value, bytes) else json.dumps(value).encode())
        self.status = status
        self.headers = Message()
        for key, item in (headers or {}).items():
            self.headers[key] = item


class Transport:
    def __init__(self, outcomes: list[Reply | Exception]):
        self.outcomes = outcomes
        self.calls: list[Request] = []

    def open(self, request: Request, timeout: float) -> Reply:
        self.calls.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def configure(
    monkeypatch: pytest.MonkeyPatch, outcomes: list[Reply | Exception]
) -> tuple[BotClient, Transport, list[float]]:
    client = BotClient("http://127.0.0.1:8000", KEY)
    transport = Transport(outcomes)
    delays: list[float] = []
    monkeypatch.setattr(client, "_opener", transport)
    monkeypatch.setattr("marketob_sdk.client.time.sleep", delays.append)
    monkeypatch.setattr("marketob_sdk.client.random.uniform", lambda _a, _b: 0)
    return client, transport, delays


def test_retries_preserve_exact_payload_and_respect_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, transport, delays = configure(
        monkeypatch,
        [
            Reply(429, {"code": "rate_limited"}, {"Retry-After": "3"}),
            URLError("synthetic"),
            Reply(503, {"code": "storage_unavailable"}),
            Reply(200, RECEIPT),
        ],
    )
    assert client.send_message(MESSAGE) == RECEIPT
    assert len(transport.calls) == 4 and delays == [3, 2, 4]
    assert len({r.data for r in transport.calls}) == 1
    assert all(r.get_header("Authorization") == "Bearer " + KEY for r in transport.calls)
    assert KEY not in repr(client)


def test_nonretryable_errors_invalid_responses_and_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, transport, _ = configure(monkeypatch, [Reply(409, {"code": "idempotency_conflict"})])
    with pytest.raises(APIError, match="idempotency_conflict"):
        client.send_message(MESSAGE)
    assert len(transport.calls) == 1
    client, _, _ = configure(monkeypatch, [Reply(400, {"code": KEY, "message": KEY})])
    with pytest.raises(APIError) as failure:
        client.send_message(MESSAGE)
    assert KEY not in str(failure.value) and failure.value.code == "api_error"
    for payload in (b"not json", {**RECEIPT, "secret": KEY}, b'{"value":NaN}', b"x" * 524289):
        client, _, _ = configure(monkeypatch, [Reply(200, payload)])
        with pytest.raises(ProtocolError):
            client.send_message(MESSAGE)
    client, _, delays = configure(monkeypatch, [URLError(KEY) for _ in range(4)])
    with pytest.raises(TransportError) as failed:
        client.send_message(MESSAGE)
    assert KEY not in str(failed.value) and len(delays) == 3
    client, transport, delays = configure(monkeypatch, [Reply(429, {}, {"Retry-After": "120"})])
    with pytest.raises(APIError) as limited:
        client.send_message(MESSAGE)
    assert limited.value.retry_after == 120 and len(transport.calls) == 1 and not delays


@pytest.mark.parametrize(
    "origin",
    [
        "http://remote.example",
        "https://user:password@example.com",
        "https://@example.com",
        "https://example.com/path",
        "https://example.com?secret=1",
        "file:///local",
        "http://api:8000",
    ],
)
def test_origins_require_tls_or_explicit_local_mode(origin: str) -> None:
    with pytest.raises(ProtocolError):
        BotClient(origin, KEY)
    BotClient("http://api:8000", KEY, allow_container_http=True)
    BotClient("https://api.example.com", KEY)


def test_registration_is_not_retried_and_query_guards_are_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, transport, delays = configure(monkeypatch, [URLError("lost exchange response")])
    with pytest.raises(TransportError):
        client.exchange_registration("mr_" + "b" * 43)
    assert len(transport.calls) == 1 and delays == []
    with pytest.raises(ProtocolError):
        client.ack("../foreign")
    with pytest.raises(ProtocolError):
        client.events(cursor="cursor", wait=1)
    with pytest.raises(ProtocolError):
        client.events(limit=101)
    with pytest.raises(ProtocolError):
        client.send_message({**MESSAGE, "price": 1})
    assert len(transport.calls) == 1


def test_real_http_redirect_never_forwards_bot_authorization() -> None:
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/capture")
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        client = BotClient("http://127.0.0.1:" + str(server.server_port), KEY)
        with pytest.raises(APIError) as failure:
            client.identity()
        assert failure.value.status == 302
        assert seen == ["/v1/bot/identity"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
