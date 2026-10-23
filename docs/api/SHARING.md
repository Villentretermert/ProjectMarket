# Sharing API · PM-017 / contract 1.0.7

87 schemas / 63 specified operations. Every route requires a local session; mutations
require CSRF and exact Origin. Sharing never transfers source data, keys or grants.

| Route under /v1 | Behavior |
|---|---|
| POST personal-pages/{page_id}/shares | Own saved version → immutable title/layout snapshot, 201 |
| GET personal-pages/{page_id}/shares | Complete list of up to 20 active owned links |
| DELETE shares/{share_id} | Own link revoked; idempotent 204 |
| POST template-imports/preview | Code → title/layout and inaccessible block IDs, 200 |
| POST template-imports | Code → independent personal page with version 1, 201 |

ShareCreate requires expected_template_version. expires_at is optional: omission gives
30 days, null means no expiry, a supplied timestamp must be in the future. Creation
and import require Idempotency-Key, 8–128 letters/digits/underscore/hyphen. Exact replay
recovers the same link/page; changed intent or deleted copy conflicts. A replay of an
already successful import can recover its copy after the link is revoked, but new
imports cannot. A stale source page version conflicts before creating a share.

The code is a random 192-bit base64url server locator (32 characters), not encryption.
It permits reading intentionally shared title/layout/references, never private source
payloads. It is stored in the private DB for owner listing/reuse. Keep it out of logs;
Web uses a URL fragment and POST body. No offline or cross-server import is supported.
Title is deliberately shared; source names and values are not embedded in references.

Preview and import check current source access; the returned preview contains no
record payloads even for readable sources. Unavailable blocks preserve positions.
The new page title gets (copy), bounded to 80 characters. Subsequent author edits do
not alter issued snapshots or imported pages. New imports recheck expiry/revocation.
Deleted/deactivated authors make links unavailable. Deleting the original page
revokes its links in the same transaction; earlier copies remain independent.

Account locks serialize creation/import. A share row lock makes revocation wait for
already-authorized imports; later imports fail. Import snapshots are validated against
the closed current layout schema. Unknown versions, injected payloads, oversized codes
and invalid fields are rejected. Missing/revoked/expired locators return generic 404.
Personal-page capacity (20) and block capacity (50) still apply. Up to 20 active links/page.

Retention of revoked snapshot metadata and deleted-account data remains in the PM-023
privacy work; there is no promise of physical erasure by the logical revoke operation.
