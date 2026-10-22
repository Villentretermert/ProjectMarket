# ADR-0010 · Bounded account favorites

Status: implemented PM-015. Source: G03 manual order, PM-015 cross-client persistence.

Use PostgreSQL references with a collection revision, an explicit exact-permutation
order operation, and separate monotonic seen data/template revisions. At most 100
saved channels per account; GET returns the whole bounded list in one response.
This is an engineering limit for the pilot, not a new user answer.

Compared with a paged ID list, one bounded collection makes manual order and concurrent
edits explicit. A future larger collection needs order tokens/pagination. Browser-only
storage cannot meet cross-client persistence. Copying titles/payloads into favorites
would create stale private metadata after revocation, so each list resolves live rights.

Unavailable references remain removable but reveal no title/slug/revision. Existing
access policy remains authoritative. New is a channel-change marker, not an unread
article count. Refresh/return/reconnect rechecks data; idle-client updates remain PM-018.
