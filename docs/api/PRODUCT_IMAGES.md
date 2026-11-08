# Product photos — S05 / contract revision 1.1.1

`Product.image` is optional source content, not a layout property. Existing
messages remain valid. Remove a photo by sending a higher `source_revision`
with the complete product payload and no `image`. Reusing a message ID with
changed image bytes or alt text returns `409 idempotency_conflict`.

```python
from pathlib import Path
from marketob_sdk import prepare_product_image

payload = {
    "title": "Hand soap",
    "description": "Gentle everyday hand wash.",
    "price": {"amount_minor": 250, "currency": "EUR"},
    "availability": "in_stock",
    "image": prepare_product_image(
        Path("soap.png").read_bytes(), "A teal bottle of hand soap"
    ),
}
# Use this payload in a normal kind=data, content_type=product message.
# Keep the same envelope/message_id and bytes when retrying an uncertain send.
```

The helper uses Python's standard library and has no network/file side effects.
The calling bot chooses and reads its own file. It removes ancillary metadata
(including EXIF/text/color profiles); it does not resize, convert JPEG, correct
orientation, or apply a color profile. Convert the photo to sRGB pixels and export
a small static RGB/RGBA PNG first. The publisher is responsible for the visible
content and permission to use it. The pilot bot includes an original synthetic
bottle illustration, explicitly labelled as demo in alt text; other items have
no image.

## Wire fields and bounds

| Field | Rule |
| --- | --- |
| `media_type` | Exactly `image/png` |
| `data_base64` | Canonical padded base64, no prefix or whitespace; ≤131072 characters / 98304 decoded bytes |
| `alt` | Plain-text description, 1–200 characters; no NUL or invalid Unicode |

Only static non-interlaced 8-bit grayscale, grayscale+alpha, RGB or RGBA PNG is
accepted. Each side is 1–512 pixels. The wire file has only IHDR, consecutive
IDAT chunks and IEND. Palette, tRNS, APNG, metadata, invalid checksums, extra data,
bad deflate streams/row filters and decoded-size mismatches are rejected.
The helper also rejects transparency chunks and animation instead of silently
altering them. Its input byte limit is the same 96 KiB, before metadata removal.

Validation runs before the durable receipt/snapshot transaction. Schema-invalid
input returns `422 invalid_request`; unsupported PNG bytes return `422 invalid_image`.
The whole JSON request is still limited to 256 KiB. No new endpoint, migration,
external downloader, thumbnail service or dependency is introduced.

## Access, privacy and compatibility

Images are returned only with authorized source content. Published-channel rules,
grant revocation, deleted sources, offline/hidden clearing and logout also apply
to photo bytes. All API responses remain `Cache-Control: no-store`. Images follow
the existing current-record, 30-day ingest-history and backup retention policies.
Revocation stops future access; it cannot retract a copy already saved by an
authorized reader.

Personal pages and shared templates contain source references only. Sharing
cannot transfer photo bytes or grant access. Profile export does not include
source content. The browser creates an inline `data:image/png;base64,…` from the
typed field; no external image URL, referrer, tracking request or server URL fetch
is supported. The CSP allows `data:` only for images; script/object/connect
restrictions remain unchanged. Missing photos use the existing text layout;
decode failures show **Photo unavailable** without hiding price/actions.

Wire `schema_version` remains `1.0`, with an optional field in contract revision
1.1.1. Upgrade the server before enabling this field in a bot: older strict
servers reject it. Older Web clients ignore the new field. A server rollback
requires disabling photo emission first. The product payload is not copied into
layouts. At the 50-block limit, photo base64 alone can reach 6.25 MiB per snapshot;
large media catalogs need a later separate media service. This work does not
claim that the deferred full load test has passed.

Format references: [W3C PNG](https://www.w3.org/TR/png-3/) and
[CSP img-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/img-src).
