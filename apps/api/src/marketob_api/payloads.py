"""Validate production input against the packaged canonical JSON Schema bundle."""

import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from marketob_api.errors import ApiError

SCHEMAS = json.loads(files("contracts").joinpath("schemas.json").read_text(encoding="utf-8"))[
    "$defs"
]
VALIDATORS = {
    name: Draft202012Validator(
        {"$defs": SCHEMAS, "$ref": "#/$defs/" + name}, format_checker=FormatChecker()
    )
    for name in (
        "Message",
        "ChannelCreate",
        "ChannelDraft",
        "Publish",
        "Rollback",
        "ActionInput",
        "Result",
        "FavoriteOrder",
        "FavoriteSeen",
        "PageWrite",
        "ShareCreate",
        "ImportInput",
        "Preference",
    )
}


def validate_payload(name: str, body: dict[str, Any]) -> None:
    if name == "Message" and body.get("schema_version") != "1.0":
        raise ApiError(422, "unsupported_schema_version", "Use supported schema version 1.0.")
    if next(VALIDATORS[name].iter_errors(body), None) is not None:
        raise ApiError(422, "invalid_request", "Request fields do not match the API schema.")
    # PostgreSQL text cannot represent NUL; reject invalid Unicode before persistence.
    wire = json.dumps(body, ensure_ascii=False, allow_nan=False)
    if contains_nul(body):
        raise ApiError(422, "invalid_text", "NUL characters are not supported.")
    try:
        wire.encode("utf-8")
    except UnicodeEncodeError:
        raise ApiError(422, "invalid_text", "Use valid Unicode text.") from None
    if name == "Message" and body.get("content_type") == "product":
        if body["payload"]["price"]["currency"] not in {"EUR", "USD", "RUB"}:
            raise ApiError(422, "unsupported_currency", "The currency is not supported.")
    if name == "Message" and body.get("content_type") == "chart":
        series = body["payload"]["series"]
        if len({item["name"] for item in series}) != len(series):
            raise ApiError(422, "duplicate_series", "Chart series names must be unique.")
        for item in series:
            xs = [point["x"] for point in item["points"]]
            if any(a >= b for a, b in zip(xs, xs[1:], strict=False)):
                raise ApiError(422, "invalid_chart_order", "Chart coordinates must increase.")


def contains_nul(value: Any) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(contains_nul(key) or contains_nul(item) for key, item in value.items())
    if isinstance(value, list):
        return any(contains_nul(item) for item in value)
    return False
