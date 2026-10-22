# Favorites API · PM-015

Implemented contract revision 1.0.5; bot wire schema remains 1.0. Cookie session,
exact allowed Origin and CSRF protect mutations. No user ID comes from the body.

| Route | Behavior |
|---|---|
| GET `/v1/favorites` | Complete ordered `{revision, items}` collection, maximum 100. Each item is authorized now. |
| PUT `/v1/favorites/{channel_id}` `{}` | Idempotent save of a readable published channel; append at end. |
| DELETE `/v1/favorites/{channel_id}` | Idempotent removal of this account's reference, even after access is lost. |
| PUT `/v1/favorites/order` | `{expected_revision, channel_ids}` must be the exact current permutation. Stale collection returns 409. |
| PUT `/v1/favorites/{channel_id}/seen` | `{data_revision, template_version}` from the rendered snapshot; monotonic, future values rejected. |

This bounded atomic collection deliberately has no pagination. It replaces the
unimplemented PM-004 paginated ID-only design so manual ordering and its concurrency
guard describe one consistent collection. The pilot limit is 100 saved channels,
not a limit on all channels or users on the server. Other list APIs keep cursors.

Readable items contain channel_id, available=true, current published title/slug,
and unread. Unavailable items contain only channel_id and available=false. Never
store titles, source payloads, or grants in favorites. Regrant restores live metadata.
Deleting a favorite neither deletes its channel nor grants/revokes source access.

A per-account advisory transaction lock serializes collection writes without a
user-row lock upgrade. Collection revision changes only on effective add/remove/order.
Seen uses greatest(previous, observed), so a delayed older client cannot make read
data unread, and an update arriving after rendering stays new. New includes changes
to published layout or channel data; it is an update marker, not a notification count.

Responses remain no-store. Foreground delivery/invalidation across idle clients is
PM-018; current Web rechecks on navigation, Refresh, visibility return and reconnect.
