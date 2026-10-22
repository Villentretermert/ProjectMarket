# Implemented channel publication API

PM-009/014 · local Python/FastAPI and PostgreSQL · contract revision 1.0.4.
The working [Web Studio](../setup/STUDIO.md) exposes this workflow. Current
[workspace roles](TEAMS.md) govern management calls; Editors cannot change audience.

## Owner workflow

All management calls require a local session, exact allowed Origin and CSRF on
mutations. The bot operational key cannot edit or publish a layout.

1. `POST /v1/channels`: bot_id, slug and title; omitted visibility defaults to
   `selected`. Explicit `public` is supported. The initial empty draft is version 1.
2. Send typed resources using the bot [ingestion API](INGESTION.md).
3. `GET /v1/owner/channels/{channel_id}/resources` lists owned live resources,
   including resources not yet bound to a layout. Each item has content_type,
   source, content, source_revision, data_revision and UTC updated_at.
4. `PUT /v1/owner/channels/{channel_id}` replaces the draft. Supply exact
   expected_template_version and next layout.template_version=current+1.
5. `GET .../preview` returns the draft with compatible current records.
6. `POST .../publish` with `{"expected_template_version":2}` validates sources
   again and atomically publishes the draft. Empty layouts are valid, including
   data_revision=0 before the first message. Publishing requires an active bot.
7. `GET /v1/channels/{slug}` returns the published snapshot. Public channels allow
   anonymous reads; selected channels allow current workspace members and explicitly granted
   users. A draft change does not change live title, visibility, blocks or actions.

Example draft replacement (replace ch_assigned with the actual ID):

```json
{
  "title": "Daily news",
  "visibility": "selected",
  "expected_template_version": 1,
  "layout": {
    "schema_version": "1.0", "template_version": 2,
    "theme": "blue", "density": "compact",
    "blocks": [{
      "block_id": "headline", "source": {"channel_id": "ch_assigned", "resource_id": "headline-001"},
      "content_type": "news", "view": "compact", "action_ids": []
    }]
  },
  "actions": []
}
```

Blocks have unique IDs, at most 50 per layout, and bind this channel only. Each
action must be used by a product block and match that product's resource ID.
The G02 pilot accepts only kind `request_purchase`, label `Request purchase`.
Cart actions are rejected. Quantity is fixed to one in PM-010. Schema 1.0 keeps
the broader vocabulary for compatibility; the local pilot applies this narrower
runtime policy explicitly. No payment is taken.

Drafts may reference missing resources to allow construction before data arrives.
Publication requires every bound source to exist with its declared type. Current
data remains live after publication. Deleted or type-changed records are omitted
from snapshots; the layout retains its reference so the client can show
`Source unavailable`. Unbound records never enter consumer snapshots. An empty
channel can show an empty state. Source timestamps and revisions indicate freshness;
they are ingestion times, not proof of upstream event or client delivery time.

## Versions, rollback and deletion

`GET .../versions` lists immutable definitions with created_at and first
published_at (null for a never-published draft). channel.published identifies the
currently published version. Previous definitions remain inspectable by the owner.
Only data references are versioned, not historical private resource payloads.

`POST .../rollback` with
`{"expected_template_version":3,"target_template_version":2}` copies a previously
published definition into version 4, revalidates it and publishes atomically.
Latest data is preserved. A removed/incompatible source fails with 409 and leaves
both draft and publication unchanged. Concurrent edits/rollback conflict with 409;
reload the draft instead of retrying with a new guessed version.

`DELETE /v1/owner/channels/{channel_id}` disables reads/ingestion, removes grants
and emits access.revoked. Repeating an owned deletion returns 204. Slugs/IDs and
source revision tombstones are reserved. Physical erasure is PM-023. Revoking the
bot disables its channels; an old publication cannot bring them back.

## Pagination and conditional reads

Owned channel, version and resource inventories accept limit=1..100 (default 100)
and cursor. Cursors are signed, session/operation/channel bound and expire in 60s.
Each scan fixes an upper sequence; new entries appear in the next scan. Live
resource values may change during a scan, and deleted entries are omitted. An
empty page with a next_cursor must still be continued. A null cursor ends the
scan. Consumer snapshots need no pagination: the layout is bounded to 50 blocks.

Snapshot responses include ETag and `Vary: Cookie, Origin`; the ETag includes the
current session audience (or anonymous), published definition and current data.
`If-None-Match` supports weak comparison/list validators and `*`. Authorization
and ordinary request validation always run before 304. An expired session gives
401, revoked private access gives 404 without an ETag, even with a known validator.
All responses remain `Cache-Control: no-store`; conditional reads support explicit
application revalidation, not shared HTTP storage. Clear private data on access
loss/logout. See [RFC 9110, preconditions](https://www.rfc-editor.org/rfc/rfc9110.html#name-evaluation).

## Verification

`tests/test_channels.py` covers real PostgreSQL publication, draft/live separation,
immutable rollback, authorization/ETag, fixed scans, default/private/empty/deleted
states, typed projections, optimistic concurrency and injected transaction failure.
`python -m scripts.smoke_channels` exercises the actual HTTP server and is included
in Docker CI. It creates synthetic test resources and deactivates its own account.
Use a disposable development instance, not a production user account.
