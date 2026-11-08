"""Bounded static PNG profile for product photos; no network or native decoder."""

import base64
import binascii
import struct
import zlib

MAX_BYTES = 96 * 1024
MAX_SIDE = 512
SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _checked_png(raw: bytes, *, strip_metadata: bool = False) -> bytes:
    if not 0 < len(raw) <= MAX_BYTES or not raw.startswith(SIGNATURE):
        raise ValueError("Use a PNG of at most 96 KiB.")
    offset, stage = 8, "header"
    kept = bytearray(SIGNATURE)
    compressed = bytearray()
    width = height = channels = 0
    while offset < len(raw):
        start = offset
        if offset + 12 > len(raw):
            raise ValueError("Truncated PNG chunk.")
        length = int.from_bytes(raw[offset : offset + 4], "big")
        kind = raw[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(raw) or any(not (65 <= x <= 90 or 97 <= x <= 122) for x in kind):
            raise ValueError("Invalid PNG chunk.")
        data = raw[offset + 8 : end - 4]
        crc = int.from_bytes(raw[end - 4 : end], "big")
        if zlib.crc32(kind + data) != crc or kind[2] & 32:
            raise ValueError("Invalid PNG checksum or reserved bit.")
        offset = end
        if stage == "header" and kind != b"IHDR":
            raise ValueError("PNG must start with IHDR.")
        if kind == b"IHDR":
            if stage != "header" or length != 13:
                raise ValueError("Invalid PNG header.")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", data
            )
            if not (1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE):
                raise ValueError("PNG sides must be between 1 and 512 pixels.")
            if (
                depth != 8
                or color not in (0, 2, 4, 6)
                or (compression, filtering, interlace) != (0, 0, 0)
            ):
                raise ValueError("Use 8-bit gray/RGB/RGBA PNG without interlace or palette.")
            channels = {0: 1, 2: 3, 4: 2, 6: 4}[color]
            stage = "data"
        elif kind == b"IDAT":
            if stage not in ("data", "idat"):
                raise ValueError("PNG IDAT chunks must be consecutive.")
            compressed.extend(data)
            stage = "idat"
        elif kind == b"IEND":
            if length or stage not in ("idat", "after") or offset != len(raw):
                raise ValueError("Invalid PNG end or trailing bytes.")
            stage = "end"
        elif strip_metadata and kind[0] & 32 and kind not in (b"acTL", b"fcTL", b"fdAT", b"tRNS"):
            # Drop text/EXIF/color profiles without decompressing their contents.
            if stage == "idat":
                stage = "after"
            continue
        else:
            raise ValueError("PNG metadata, animation and extra chunks are not accepted.")
        kept.extend(raw[start:end])
    if stage != "end" or not compressed:
        raise ValueError("Incomplete PNG.")
    stride = width * channels + 1
    expected = stride * height
    decoder = zlib.decompressobj()
    try:
        # One extra byte detects excessive expansion; never call unbounded flush().
        pixels = decoder.decompress(bytes(compressed), expected + 1)
    except zlib.error:
        raise ValueError("Invalid PNG compression.") from None
    if len(pixels) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("PNG decoded size does not match its dimensions.")
    if any(pixels[row] > 4 for row in range(0, expected, stride)):
        raise ValueError("Invalid PNG row filter.")
    return bytes(kept)


def validate_product_image(encoded: str) -> None:
    """Validate canonical base64 and the exact PNG bytes persisted by ingestion."""
    if not encoded or len(encoded) > MAX_BYTES * 4 // 3:
        raise ValueError("Image exceeds the encoded size limit.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError, binascii.Error:
        raise ValueError("Use canonical base64 PNG bytes.") from None
    if base64.b64encode(raw).decode("ascii") != encoded:
        raise ValueError("Use canonical base64 PNG bytes.")
    _checked_png(raw)


def prepare_product_image(raw: bytes, alt: str) -> dict[str, str]:
    """Bot-side helper: remove PNG metadata, validate bounds, package for Product.image."""
    if not isinstance(alt, str) or not 1 <= len(alt) <= 200 or "\x00" in alt:
        raise ValueError("Provide a plain-text image description (1–200 characters).")
    alt.encode("utf-8")
    clean = _checked_png(raw, strip_metadata=True)
    return {
        "media_type": "image/png",
        "data_base64": base64.b64encode(clean).decode("ascii"),
        "alt": alt,
    }
