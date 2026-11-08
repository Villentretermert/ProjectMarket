"""Original synthetic raster illustration, not a real product photograph."""

import struct
import zlib

from marketob_sdk import prepare_product_image


def soap_image() -> dict[str, str]:
    size = 160
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # PNG filter: none.
        for x in range(size):
            color = (235, 244, 247)
            if 46 <= x < 114 and 42 <= y < 140:
                color = (31, 121 + (x - 46) // 4, 119)
            if 58 <= x < 102 and 24 <= y < 42:
                color = (24, 57, 69)
            if 80 <= x < 120 and 20 <= y < 28:
                color = (24, 57, 69)
            if 50 <= x < 110 and 77 <= y < 116:
                color = (250, 248, 228)
            rows.extend(color)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    raw = b"\x89PNG\r\n\x1a\n"
    raw += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    raw += chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b"")
    return prepare_product_image(raw, "Demo illustration: a teal hand soap bottle")
