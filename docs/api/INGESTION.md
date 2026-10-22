# Implemented ingestion API

PM-008 · Python/FastAPI + PostgreSQL · local pilot.
The canonical `Message`, `ChannelCreate`, `Channel` and `Receipt` schemas are
packaged with the API. Runtime validation uses the checked-in JSON Schema bundle,
not the single-process reference model. See [PROTOCOL.md](PROTOCOL.md) for ordering.

## Provision a source

A signed-in business owner sends `POST /v1/channels` with cookie, Origin and CSRF:

```json
{"bot_id":"bot_from_registration","slug":"pilot-news","title":"Pilot news","visibility":"selected"}
```

Response 201 contains a server channel ID, an empty compact layout at version 1,
no actions and `published=false`. A bot must belong to the caller. Slugs are unique
and never reveal a conflicting channel's private metadata. The draft accepts bot
data. Publish/update and consumer snapshots are PM-009; this endpoint alone never
makes a channel publicly readable. Bot creation/key exchange: [BOT_REGISTRATION.md](BOT_REGISTRATION.md).

## Send messages

`POST /v1/bot/messages`, JSON UTF-8, operational Bearer key with `messages:write`.
No user session is needed. Example, using IDs assigned by this local server:

```json
{"schema_version":"1.0","message_id":"news-001","channel_id":"ch_assigned","resource_id":"headline-001","source_revision":1,"occurred_at":"2026-10-22T12:00:00Z","kind":"text","payload":{"title":"Pilot update","body":"A synthetic local news item."}}
```

Success is HTTP 200 `Receipt`: message_id, receipt_id, server data_revision and
UTC received_at. It is emitted only after database commit. Text normalizes to
news; data replaces news/product/chart; delete removes content and keeps a
source-revision tombstone. Event hints require an existing live resource and
advance the channel revision without changing its content/source_revision.

Identity and source ownership are checked before receipt replay. Same bot +
message_id + body returns the original receipt for 30 days. Object key order and
whitespace are ignored; numeric representation `1` versus `1.0` conflicts. Another
body returns 409 idempotency_conflict. A new message with source_revision <= the
current version returns 409 stale_source_revision; occurred_at is never used to
overwrite newer data. A higher version may deliberately recreate deleted content.

All source, receipt, history, counter and outbox writes share one transaction.
The bot row serializes retries across its channels; the channel access row also
serializes content changes with revocation. Different bots run independently,
apart from the short aggregate quota transaction. Outbox contains identifiers and
revision only, not payload or credentials. Its consumer is implemented later.

## Limits and retention

- 262144 bytes per uncompressed JSON body; unsupported encoding/duplicate keys/
  nonfinite numbers fail. Closed schemas reject unknown fields and versions.
- News/product text <=20000 characters; chart <=5 uniquely named series, <=1000
  points/series with strictly increasing x. EUR/USD/RUB use integer minor units.
- Unicode must be valid; NUL characters are rejected with 422 before storage.
- Continuous token buckets: 60/min/bot, burst 60; aggregate 1000/min, burst 1000.
  Settings: MARKETOB_INGEST_BOT_PER_MINUTE / MARKETOB_INGEST_TOTAL_PER_MINUTE.
  Authenticated attempts, including replay and invalid payloads, consume quota;
  a rejected empty bucket consumes neither bucket. Counters survive API restart.
- 429 supplies Retry-After. Retry the same message after backoff; use the original
  identity after an ambiguous network/503 response. Never replace it blindly.
- Raw history is removed after 7 days, receipt dedup after 30 days by the local
  maintenance worker (5000 rows/table/pass, every 60s). Expired receipts are not
  replayed even before a cleanup pass. Latest content and tombstones remain.

Compose starts maintenance automatically. For direct Python start a second process
`python -m marketob_api.maintenance`; `--once` performs one bounded cleanup pass.
If maintenance is stopped, physical retention cleanup pauses; monitor its output.
It logs counts and safe failures only. Account/source erasure and backup policies
remain PM-023/021; account deactivation currently prevents access immediately.

## Verification and current boundary

`tests/test_ingestion.py` exercises concurrent writes, retries, injected database
failure/rollback, quota persistence, tenant/bot isolation, typed payloads and
retention on PostgreSQL. `scripts/smoke_ingestion.py --phase before` writes synthetic
data and a short burst report; after an API/database restart run `--phase after`.
Only use a disposable test instance. The ignored state file contains ephemeral
test credentials; never publish it. The after phase removes it and deactivates the
test account. The report contains no credentials or source content.

The short burst is not a sustained capacity result, client delivery latency or
proof of backup recovery. Product read UI, actions, GET events and pilot bots
remain future tasks. The PM-003 visual prototype still uses synthetic in-memory data.
