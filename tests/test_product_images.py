"""Exercise the bounded photo transport, hostile files and reference/runtime parity."""

import base64
import struct
import zlib
from copy import deepcopy
from typing import Any

import pytest
from contracts.product_image import MAX_BYTES, prepare_product_image, validate_product_image
from contracts.reference_model import validate
from marketob_api.errors import ApiError
from marketob_api.payloads import validate_payload
from marketob_bots.catalog import PRODUCTS


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png(
    width: int = 2,
    height: int = 2,
    color: int = 2,
    depth: int = 8,
    pixels: bytes | None = None,
    extra: bytes = b"",
    interlace: int = 0,
) -> bytes:
    data = (
        pixels
        if pixels is not None
        else b"\0" * ((width * {0: 1, 2: 3, 4: 2, 6: 4}.get(color, 3) + 1) * height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, interlace))
        + extra
        + chunk(b"IDAT", zlib.compress(data))
        + chunk(b"IEND", b"")
    )


def encoded(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def product_message() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "message_id": "photo_one",
        "channel_id": "photo_shop",
        "resource_id": "soap",
        "source_revision": 1,
        "occurred_at": "2026-11-08T00:00:00Z",
        "kind": "data",
        "content_type": "product",
        "payload": deepcopy(PRODUCTS["soap"]),
    }


@pytest.mark.parametrize("color", [0, 2, 4, 6])
def test_supported_pixels_and_boundaries(color: int) -> None:
    for size in (1, 2, 512):
        image = prepare_product_image(png(size, size, color), "Photo")
        validate_product_image(image["data_base64"])


def test_helper_removes_metadata_without_touching_pixels() -> None:
    extra = chunk(b"eXIf", b"private GPS") + chunk(b"tEXt", b"Author\0Private")
    raw = png(extra=extra)
    with pytest.raises(ValueError):
        validate_product_image(encoded(raw))
    image = prepare_product_image(raw, "Plain product description")
    assert base64.b64decode(image["data_base64"]) == png()
    validate_product_image(image["data_base64"])


@pytest.mark.parametrize(
    "raw",
    [
        b"<svg onload='alert(1)'/>",
        b"https://example.com/tracker.png",
        b"\xff\xd8jpeg",
        png()[:-1],
        png() + b"extra",
        png()[:30] + b"broken",
        png(width=0),
        png(width=513),
        png(height=513),
        png(color=3),
        png(depth=16),
        png(interlace=1),
        png(pixels=b"\0" * 50000),
        png(pixels=b"\0"),
        png(pixels=b"\5" + b"\0" * 13),
        png(extra=chunk(b"acTL", b"animation")),
        png(extra=chunk(b"tRNS", b"\0\0")),
        png(extra=chunk(b"PLTE", b"RGB")),
        png() + b"\0" * MAX_BYTES,
        png(extra=chunk(b"IHDR", b"duplicate")),
    ],
    ids=lambda raw: f"file-{len(raw)}",
)
def test_rejects_malformed_or_unsupported_png(raw: bytes) -> None:
    with pytest.raises(ValueError):
        validate_product_image(encoded(raw))


@pytest.mark.parametrize(
    "data",
    [
        "",
        "https://example.com/a",
        "file:///a",
        "javascript:alert(1)",
        "data:image/svg+xml;base64,AAAA",
        "AAAA\n",
        "A" * (MAX_BYTES * 4 // 3 + 4),
        "%%%=",
    ],
    ids=lambda data: f"encoded-{len(data)}",
)
def test_rejects_non_base64_and_urls(data: str) -> None:
    with pytest.raises(ValueError):
        validate_product_image(data)


def test_rejects_extra_zlib_stream_and_noncontiguous_idat() -> None:
    header = png()[:33]
    first = chunk(b"IDAT", zlib.compress(b"\0" * 14))
    end = chunk(b"IEND", b"")
    for raw in (
        header + chunk(b"IDAT", zlib.compress(b"\0" * 14) * 2) + end,
        header + first + chunk(b"tEXt", b"note\0x") + first + end,
    ):
        with pytest.raises(ValueError):
            prepare_product_image(raw, "Photo")


def test_schema_reference_and_production_accept_old_and_new_messages() -> None:
    body = product_message()
    for with_photo in (True, False):
        if not with_photo:
            body["payload"].pop("image")
        validate("Message", body)  # type: ignore[no-untyped-call]
        validate_payload("Message", body)


def test_production_rejects_invalid_bytes_and_image_url() -> None:
    body = product_message()
    body["payload"]["image"]["data_base64"] = encoded(png() + b"extra")
    with pytest.raises(ApiError) as error:
        validate_payload("Message", body)
    assert error.value.code == "invalid_image"
    body["payload"]["image"] = {"url": "https://example.com/private"}
    with pytest.raises(ApiError):
        validate_payload("Message", body)


def test_helper_requires_accessible_plain_text_description() -> None:
    for alt in ("", "a" * 201, "null\0", "\ud800"):
        with pytest.raises(ValueError):
            prepare_product_image(png(), alt)
