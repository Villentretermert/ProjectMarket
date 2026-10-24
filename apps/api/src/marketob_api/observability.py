"""Allowlisted JSON events. Never format arbitrary messages, URLs, headers or exceptions."""

import json
import logging
import time
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from marketob_api.errors import ApiError, error_response

LOGGER = logging.getLogger("marketob.operations")
FIELDS = {
    "event",
    "request_id",
    "bot_id",
    "route",
    "method",
    "status",
    "duration_ms",
    "history",
    "receipts",
    "outbox",
    "unknown",
    "requests",
    "privacy_preferences",
    "privacy_updates",
    "error_class",
}


class SafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = {k: v for k, v in record.__dict__.items() if k in FIELDS}
        event.setdefault("event", "runtime")
        event.update(
            time=datetime.fromtimestamp(record.created, UTC).isoformat(),
            level=record.levelname,
            process=record.process,
        )
        return json.dumps(event, separators=(",", ":"))


def configure_logging(level: str, directory: Path | None = None, service: str = "api") -> None:
    handler: logging.Handler
    if directory:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            directory / f"{service}.jsonl",
            maxBytes=10 * 1024 * 1024,
            backupCount=4,
            encoding="utf-8",
        )
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(SafeFormatter())
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)
    logging.getLogger("psycopg.pool").setLevel(logging.WARNING)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


class ObservationMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = 499
        started = False

        async def observe(message: Message) -> None:
            nonlocal status, started
            if message["type"] == "http.response.start":
                status, started = message["status"], True
            await send(message)

        try:
            await self.app(scope, receive, observe)
        except Exception:
            # No traceback or exception message: those can contain payloads and credentials.
            status = 500
            if not started:
                await error_response(
                    ApiError(500, "internal_error", "The request failed."),
                    scope.get("state", {}).get("request_id", "unavailable"),
                )(scope, receive, observe)
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            state = scope.get("state", {})
            LOGGER.info(
                "http",
                extra={
                    "event": "http",
                    "route": route,
                    "method": scope["method"]
                    if scope["method"]
                    in {"GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"}
                    else "OTHER",
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 3),
                    "request_id": state.get("request_id"),
                    "bot_id": state.get("bot_id"),
                },
            )
