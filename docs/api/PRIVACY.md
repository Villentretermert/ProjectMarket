# Personal data and ownership · PM-023 / D46

Contract revision **1.1.0** changes account deletion: clients must send
`{"password":"…","confirmation":"DELETE"}` and transfer active owned workspaces
first. Bot messages, keys and wire schema version `1.0` are unchanged.

All routes require a current local session. Mutations also require exact Origin
and X-CSRF-Token. Responses are no-store; credential fields are write-only.

| Route | Result |
| --- | --- |
| GET /v1/account/export?section=profile | Own user_id, username, display_name, created_at |
| GET /v1/account/export?section=favorites | Own ordered channel references and seen revisions; at most100 |
| GET /v1/account/export?section=spaces | Own active page_id/title/layout; at most20 |
| GET /v1/account/export?section=requests | Own request IDs, source/action references, observed revision, quantity, state and timestamps |
| GET /v1/account/export?section=events | Own channel/event preferences |
| GET /v1/account/deletion-preview | Active owned workspaces, active personal-page and unresolved-request counts, can_delete |
| POST /v1/workspaces/{org_id}/ownership | `{username,password}` → org_id, new owner_user_id, former owner's role=admin |
| DELETE /v1/account | Password + exact DELETE; 204 only after guarded transaction commits |

Export pages have schema_version, section, items, next_cursor, exported_at.
Requests and Events accept limit1–100 (default100), cursor fixed to an upper
sequence, section and session, TTL10min. Continue until next_cursor=null; malformed,
foreign or cross-section cursor400, expired410. Restart the whole export after
failure. The bounded profile/favorites/spaces sections are returned in full.
This is a live multi-request export: timestamps/statuses may change between pages;
it is not a point-in-time database backup. Rows removed by retention during the
scan are not recoverable. The Web assembles all sections before downloading one
JSON file; error/cancellation produces no partial download. Web limit50MiB; larger
exports can use the paginated API. Rate limits still apply.

Explicit projections exclude passwords/hashes, cookies/CSRF, bot credentials,
actor aliases, idempotency keys/body hashes, other users' records and source
payloads. Request summaries/external references are excluded because they may
contain source data whose access has since been revoked. Layouts and source IDs
are the user's references, not authorization. Shared link secrets are not exported.

Only the current Owner can transfer, to a different active **Admin already in
the same workspace**. Editors/nonmembers/self/deleted recipients are rejected;
the recipient must not own another workspace (existing one-owned-workspace limit,
including legacy inactive organizations). Password verification is rate-limited.
Invalid password403 `password_confirmation_failed`; unready recipient409
`transfer_target_invalid`; existing owner409 `workspace_owner_limit`.
Team/owner columns and resync marker change in one transaction; errors roll back
everything. Former Owner becomes Admin, so replays by that account return403;
after a lost reply, GET workspaces/members to inspect actual state before retrying.
Bots, keys, grants, channel IDs and published data continue unchanged. If the old
owner knows a bot key, the new owner can rotate it separately in Studio.

Deletion preview is advisory. DELETE locks and rechecks ownership; even an empty
active workspace blocks with409 `ownership_transfer_required`. Password errors
are403 and do not revoke the session; missing/wrong confirmation422. A transfer
and recipient deletion serialize: there is no committed active workspace owned
by a deleted recipient. After deletion, sessions/grants/memberships and personal
favorites/pages/shares/preferences are removed. Own outbox hints are erased and
an atomic resync marker is written. Other users' imports, data and events remain.
Own unACKed requests cancel; ACKed unfinished requests become unknown for
reconciliation. Existing terminal records remain under30-day retention; unresolved
records are not erased just because they are old. Username/ID remain reserved,
password hash is cleared, display_name becomes Deleted user. External bots,
downloads and operator backups are outside this transaction.
