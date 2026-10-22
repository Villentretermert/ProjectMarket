"""Bound JSON input before parsing; enforce the closed local v1 transport contract."""

import json
import math
from typing import Any
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from marketob_api.errors import ApiError, error_response


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def finite_number(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("nonfinite number")
    return parsed


class ProtocolMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = "req_" + uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def safe_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["X-Request-ID"] = request_id
            await send(message)

        if not scope["path"].startswith("/v1/"):
            await self.app(scope, receive, safe_send)
            return
        body = bytearray()
        headers = Headers(scope=scope)
        try:
            if headers.get("content-encoding", "identity") != "identity":
                raise ApiError(
                    415, "unsupported_encoding", "Compressed request bodies are unsupported."
                )
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > 262144:
                    raise ApiError(413, "payload_too_large", "Request exceeds 256 KiB.")
                if not message.get("more_body", False):
                    break
            if body:
                if headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
                    raise ApiError(415, "unsupported_media_type", "Use application/json.")
                try:
                    json.loads(
                        body.decode("utf-8"),
                        object_pairs_hook=unique_object,
                        parse_constant=finite_number,
                        parse_float=finite_number,
                    )
                except ValueError, RecursionError:
                    raise ApiError(
                        400, "invalid_json", "Use valid UTF-8 JSON with unique keys."
                    ) from None
        except ApiError as error:
            await error_response(error, request_id)(scope, receive, safe_send)
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, safe_send)
