# Local identity API — PM-006

The pilot uses local accounts without Google, email or Firebase. The accepted
protocol is extended additively as **1.0.4**: the existing wire `schema_version`
remains `1.0`. Runtime `/openapi.json` lists implemented operations; the complete
planned contract remains in `packages/contracts` (80 schemas / 59 operations).

## Registration and sessions

`POST /v1/auth/register`: `username`, `password`, `display_name`. Usernames are
lowercase `[a-z0-9_-]`, 3–40 characters; passwords 12–128, display names 1–80.
`POST /v1/auth/login` accepts only username/password. Unknown fields are rejected.
Both require an exact configured `Origin` and return the existing `Session` shape.
The server sets an opaque random `marketob_session` cookie; no bearer user JWT.

`GET /v1/auth/session` returns public user metadata, expiry in UTC and a CSRF token.
Use a cookie jar; do not copy the cookie into layouts, bot messages or browser
localStorage. Cookie attributes: HttpOnly, SameSite=Strict, Path=/, max-age 24h;
Secure on HTTPS origins, explicit exception for local HTTP origins. CSRF is
derived from the session token; the database holds only the session verifier.
Passwords use salted Argon2id; existing hashes are upgraded after successful login.

Unsafe session operations require both exact `Origin` and `X-CSRF-Token`.
Sessions are bound to the issuing configured UI origin. A cookie issued through
one origin is rejected at another; this is the local client boundary, not a claim
that Google issuer/audience checks or Android secure storage have been verified.
Same-origin browser GET may omit Origin and uses the API base origin.

`DELETE /v1/auth/session` revokes that session in PostgreSQL before returning 204
and clearing the cookie. Other devices keep their own sessions. Expired/revoked
and forged credentials return 401. Wrong password and absent username share the
same safe login error. PostgreSQL-backed rate counters survive API restarts:
auth 10/min/IP, reads 120/min/session, writes 60/min/user. 429 includes Retry-After.
The development server disables proxy-header trust; spoofed forwarding headers
do not replace the peer address for the login quota.

## Personal B2B workspace

`PUT /v1/account/business-profile` with `{"name":"My shop"}` enables or renames
the signed-in user's own workspace. `GET` returns `org_id`, `name`, `role=owner`.
Both organization identity and membership come from the server. There is one
personal owner organization per account; arbitrary `org_id`, `user_id` or `role`
input is rejected. The same account can consume other sources as B2C.

[Workspace teams](TEAMS.md) use Owner/Admin/Editor and exact registered usernames.
Owner membership is created with the workspace, never granted by a read invitation. Email invitations,
email recovery and password reset delivery are deferred; no unconfigured SMTP or
hidden Google dependency exists. Do not use a shared demo password for real users.

## Selected-user access

A signed-in B2B Owner/Admin can resolve an exact username using
`GET /v1/users/by-username/{username}`. Only public `User` metadata is returned;
deleted accounts are unavailable. There is no unauthenticated user directory.

- `PUT /v1/owner/channels/{channel_id}/grants/{user_id}` with `{}` grants read
  access to an existing user. Repetition is idempotent.
- `DELETE` revokes the grant transactionally and writes an access invalidation
  to the outbox. Repeated deletion by the owner is harmless.
- `GET /v1/owner/channels/{channel_id}/grants?limit=100` lists owned grants using
  a signed 60-second fixed scan. Cursor binding includes the current session and
  channel; altered/foreign cursors fail, expired scans must restart.

The shared access policy distinguishes owner management from published source
reading. Public published sources allow anonymous reads. Selected sources allow
the owner or an explicit reader; unauthorized readers receive generic 404 without
private metadata. A grant never transfers ownership. Checks and source operations
share a transaction; a channel row lock serializes grant/visibility changes.

PM-006 implements access records and grant endpoints, **not channel creation,
content publishing or snapshot HTTP reads**. Integration tests seed synthetic
access records and exercise the actual PostgreSQL policy. Subsequent channel
routes must call the same policy. Actions do not exist yet; their cancellation
on revoke will be added transactionally in PM-010 before those routes are enabled.

## Account deactivation policy

`DELETE /v1/account` requires current session/CSRF/origin plus `{"password":"…"}`.
The transaction revokes all sessions, clears password hash and display name,
removes memberships and received grants, and disables owned sources/workspace.
Invalidations are recorded. The opaque user ID and reserved username remain as
tombstones to prevent identity reuse; this is logical account deactivation,
not physical erasure of historical business records or backups. Payload/backup
retention and cleanup remain governed by the pilot targets and later storage tasks.
Email recovery of a deactivated account is not implemented.

## Transport and storage

All v1 responses are no-store and errors follow the safe `Error` envelope.
Input is capped at 256 KiB; duplicate JSON keys, NaN/infinity, invalid UTF-8,
unsupported content encodings and unknown fields are rejected. Credentials and
input validation details are never included in error JSON. CORS uses exact origins.

Migrations run through `python -m marketob_api.migrate`. They acquire an advisory
lock and commit atomically; checksums detect changed applied SQL. Compose runs a
one-shot migration service before starting API. For direct Python startup, apply
migrations once after setting local DATABASE_URL. No database connection or secret
is needed for importing the app or ordinary unit tests.
