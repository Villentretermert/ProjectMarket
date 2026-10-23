# Foreground updates · contract 1.0.8

Implemented in PM-018 for authenticated, visible Web consumer screens. Studio has
explicit refresh. No background push, Web Push, Firebase, SSE or WebSocket endpoint.

## Read and resume

1. `GET /v1/updates` without cursor establishes the current watermark, returns an
   empty event list and a session-bound signed `next_cursor`.
2. **Then** load the authorized channel/personal-page snapshots.
3. Every 2s: `GET /v1/updates?cursor=…&watch=ch_one&watch=ch_two`. Up to 50 distinct
   visible channel IDs. IDs must match the contract identifier format. Watch is an
   interest hint and never grants read permission.
4. Apply hints by fetching current authorized snapshots or the existing request
   with GET. Commit the returned cursor only after successful application.
5. `has_more=true` drains the next batch promptly. A batch scans at most 50 durable
   changes and may additionally contain up to 50 access invalidations. Even an empty
   batch advances past unrelated changes. There is no long polling or ACK endpoint.

The rolling cursor TTL is 10 minutes. Malformed/tampered/foreign-session cursor:
400 `invalid_cursor`; expired cursor:410 `cursor_expired`; watermark older than a
cursor (for example a restored database):410 `resync_required`. Bootstrap again
before snapshot resync. Logout/session expiry requires sign-in and a fresh cursor.
429 has Retry-After, honored by the client. A cursor is held only in memory.

## Payload

`UpdatePage = {items, next_cursor, has_more}`. Each Update has:

| Field | Meaning |
|---|---|
| update_id | Stable delivery identity for deduplication; no business data |
| kind | channel.changed, request.status or access.revoked |
| channel_id | Currently authorized source, or a source already referenced by this caller |
| target_id | Channel ID or caller's own action_request_id |
| revision | Channel data revision; 0 means fetch without a revision comparison |
| event_name | news.published / catalog.changed / request.status / null |
| notify | Selected by this user and authorized at read time |

Payload excludes source titles, bodies, prices, request summaries and credentials.
All hints mean **fetch current state**; they are not ordered source snapshots and
must not roll the UI back to their revision. Old revocation followed by restored
permission becomes channel.changed. Inaccessible visible sources produce a stable
access.revoked hint even when there are no new outbox rows.

Interests are the caller's favorites, personal-page source references, explicit
preferences and visible watch IDs. Own request statuses also express interest.
Another user's request is never delivered, including to the workspace owner.
Current read rights are checked inside the read transaction. Preferences and
shared layouts do not replace those rights.

## Event preferences

- `GET /v1/preferences/{channel_id}` returns the saved preference or default
  `{"channel_id":"…","events":["request.status"]}` for an accessible channel.
- `PUT /v1/preferences/{channel_id}` accepts that same closed schema. The path and
  body channel IDs must match; events are unique, max3. An empty list disables toasts.
- `GET /v1/preferences?limit=100&cursor=…` lists explicit, currently accessible
  preferences using the existing session-bound fixed-scan pagination.

News upsert/text produces news.published; product upsert produces catalog.changed.
Explicit bot event messages can emit either event. Chart/deletion/publication/grant
changes refresh silently. Request-state events only notify their actor by default.
Preferences control notifications, **not** consistency refreshes. Notifications are
generic in-app toasts; there is no durable notification inbox or exactly-once toast
guarantee across tab reloads. In-session replay is deduplicated in bounded memory.

## Storage and future Android boundary

Migration010 adds event_preferences, delivery_state and delivery order metadata on
the existing transactional outbox. A short serialized transaction numbers only
committed rows. It releases its global lock before caller/channel authorization;
late commits receive later delivery positions. Existing outbox rows are retained;
physical outbox minimization is tracked for PM-023. Cursor expiry bounds replay
promises independently of physical retention.

Future Android foreground clients must use the same bootstrap-before-snapshot,
session binding, deduplication, Retry-After, source revalidation and logout clearing.
A future push provider may send a generic wake-up hint; neither that hint nor a
device token grants read rights. Background delivery/device enrollment is absent
and must be separately designed and tested in its authorized phase.

[ADR](../adr/0013-live-updates.md) · [Web guide](../setup/LIVE_UPDATES.md).
