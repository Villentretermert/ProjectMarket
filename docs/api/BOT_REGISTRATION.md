# Implemented bot registration API

PM-007 · local pilot · contract revision 1.0.2, wire `schema_version=1.0` unchanged.
Use loopback HTTP locally. Remote deployments require HTTPS. User registration
and business profile setup are described in [IDENTITY.md](IDENTITY.md).

1. As a signed-in business owner, `POST /v1/bots {"name":"Catalog"}` with the
   session cookie, allowed Origin and `X-CSRF-Token`. Response 201 is `Registration`.
2. Pass its `registration_credential` to that bot through a private configuration
   channel. It expires in 15 minutes and can only be exchanged once.
3. The bot sends `POST /v1/bot-registrations/exchange {}` with
   `Authorization: Bearer <registration_credential>`, without a user cookie.
4. Store the returned `api_key` outside source control. It expires in 90 days.
   `GET /v1/bot/identity` verifies it and returns bot/key IDs, scopes and expiry.
   Neither the owner cookie nor password belongs in a bot.

Registration and operational tokens use different namespaces and cannot replace
one another. 256 random bits are generated; only SHA-256 verifiers and a public
12-character prefix are stored. Raw secrets are returned only when issued, with
`Cache-Control: no-store`. The API never logs request bodies/authorization headers.
Initial scopes are `messages:write`, `events:read`, `events:ack`, `events:result`.
This task implements their credential policy; messages and events follow in
PM-008/010. `GET /v1/bot/identity` accepts any live operational key.

## Owner management

| Operation | Behaviour |
|---|---|
| GET /v1/bots | Only owned bots; bounded signed fixed-scan pagination |
| GET /v1/bots/{bot_id} | Owned metadata plus nullable UTC last_seen |
| POST /v1/bots/{bot_id}/registration {} | Replace outstanding registration, preserve working keys |
| POST /v1/bots/{bot_id}/keys | Issue narrowed scopes; optional replaces_key_id revokes old key atomically |
| GET /v1/bots/{bot_id}/keys | Metadata only, never raw secrets; pagination |
| DELETE /v1/bots/{bot_id}/keys/{key_id} | Immediate key revocation |
| DELETE /v1/bots/{bot_id} | Irreversible bot revocation; disable its keys and channels |

`KeyIssue`: `{"scopes":["messages:write"]}`; include a valid `replaces_key_id`
only when rotating an existing key of this bot. Duplicate/unknown scopes fail.
A pending bot must exchange registration first. A revoked bot cannot be renewed;
create a new bot. Lost exchange/key responses require the owner to issue a new
key; a consumed bootstrap token never reveals its old operational secret again.

Read grants do not confer management access. Bot identity and organization come
from the verifier, not request fields. Foreign objects return generic 404; B2C
management attempts return 403. Account deactivation makes all owned bot calls
fail through the active-organization check. Rotation and bot calls serialize on
the bot row: requests completed before revocation may succeed, later ones fail.

Bootstrap attempts use the configured auth limit (default 10/min/IP). Identity
reads use `MARKETOB_BOT_READ_RATE_LIMIT` (default 60/min/bot), durable across API
restarts; owner reads/writes use session/user limits. Return 429 + Retry-After.
These fixed-minute limits are not a sustained-load result. Message-specific
token buckets and aggregate ingress limits are implemented in PM-008.

This is a backend API. Studio UI integration follows in PM-014; no Android build
or external service is required. Do not put real credentials in issues or examples.
