# Bot API draft — MarkeTOB

**Historical draft; superseded by [API 1.0](api/PROTOCOL.md) and [validated OpenAPI](../contracts/openapi.json).** PM-004 is complete as a contract task; PM-007–012 implement the server. This draft is retained for context, not as the current protocol. Public developer documentation is in English so developers and AI tools can use the same contract.

## Authentication and registration

A human B2B owner signs in with a local account (Google identity is deferred for the local-only pilot), creates a bot, and obtains a unique one-time registration credential bound to that bot. A proposed exchange issues a scoped operational key. Registration credentials and operational keys have distinct purposes. All bots, local or external, use HTTPS and their own keys. Store server-side key digests; expose raw keys only on issuance. Rotation and revocation invalidate access according to a documented transition policy.

Operational bot calls use `Authorization: Bearer <BOT_API_KEY>`. User sessions never reuse a bot key. Never put credentials in URLs, shared templates, browser storage or logs. The owner management routes, local session flow and limits are finalized in PM-004/006.

## Proposed endpoints

| Caller | Method / route | Purpose |
|---|---|---|
| Owner | POST /v1/bots | Create an owned bot and start registration |
| Bot bootstrap | POST /v1/bot-registrations/exchange | Exchange one-time bot registration credential |
| Owner | POST /v1/bots/{bot_id}/keys | Issue or rotate a scoped key |
| Owner | DELETE /v1/bots/{bot_id}/keys/{key_id} | Revoke a key |
| Bot | POST /v1/bot/messages | Send text, typed JSON data, or an event |
| Bot | GET /v1/bot/events?cursor=...&limit=...&wait=... | Retrieve pending user actions; bounded optional long polling |
| Bot | POST /v1/bot/events/{event_id}/ack | Acknowledge durable receipt; not business success |
| Bot | POST /v1/bot/events/{event_id}/result | Report business state/result with stable request ID |
| User | GET /v1/channels/{slug} | Read published layout and allowed snapshot |
| User | POST /v1/channels/{id}/actions | Request a registered action |
| User | GET /v1/action-requests/{id} | Read own action status |
| User | GET /v1/updates | Subscribe to allowed changes (transport decided by ADR) |
| User | POST /v1/personal-pages/{id}/shares | Create a template-only share |
| User | POST /v1/template-imports | Import into own account, rechecking source access |

Routes are versioned and subject to PM-004. Management CRUD for pages, grants, favorites, personal pages, preferences and devices must also be included in the complete OpenAPI. Bot identity is derived from the verified key, not trusted from a submitted bot_id.

## Message example

```json
{
  "schema_version": "1.0",
  "message_id": "catalog-item-42-r7",
  "kind": "data",
  "channel_id": "ch_catalog",
  "resource_id": "item_42",
  "source_revision": 7,
  "operation": "upsert",
  "content_type": "product",
  "payload": {
    "title": "Daily notebook",
    "description": "A5, dotted pages",
    "price": {"amount_minor": 1800, "currency": "EUR"},
    "availability": "in_stock"
  }
}
```

The values are demo data. `kind=text` carries bounded text; `kind=data` carries a typed JSON payload; `kind=event` carries a named event and schema-validated fields. Their discriminated union, timestamps, delete semantics, maximum size and required fields must be finalized in PM-004. The server rejects a channel the key cannot write. Monetary values have explicit currency/units; chart data declares axes, types and units. A product is not a confirmed offer/payment merely because it was displayed.

## Data-to-UI contract

A page has schema_version, template_version, allowed block IDs, types, bindings and action IDs. A data snapshot has a separate data_revision. Bindings reference allowlisted fields and owned/authorized sources; they contain no JavaScript, Python, SQL or arbitrary outbound URLs. Human text is rendered safely. Chart data can switch only between compatible chart representations; text cannot silently become numerical evidence.

## Action and GET delivery

A client action contains action_id, resource_id, observed revision, validated inputs and an idempotency key. Server-side ownership, visibility, current resource rules and action permissions are authoritative. The bot receives event_id, action_request_id, a bounded actor reference, event type, resource and validated inputs. It does not receive Google tokens or a user's full profile by default.

GET returns pending events and an opaque pagination cursor. Reading does not delete or mark success. A cursor is a paging position, not an acknowledgement: unacknowledged events remain eligible for redelivery after the defined retry interval; the consumer must not permanently skip them by advancing a stored cursor. ACK is a separate idempotent operation after the bot durably records receipt. If receipt is acknowledged but business execution fails, the request stays nonterminal until result/timeout/reconciliation policy resolves it. Exact retry, expiry, pagination and reconciliation rules are part of PM-004.

Delivery is **at least once**, not exactly once. The bot must deduplicate side effects using action_request_id/event_id. External order APIs should accept the same idempotency key or expose status lookup. Do not automatically repeat an ambiguous purchase side effect without reconciliation. The pilot creates requests only; there are no built-in charges.

## Errors, retries and observability

Use stable machine codes plus a safe message and request_id. Define 400/422 validation, 401 authentication, 403 access, 404 unavailable resource, 409 version/idempotency conflict, 413 size and 429 rate limit (Retry-After). Unknown schema versions fail explicitly. Retrying a message_id with a changed body is a conflict, not a silent overwrite. Server-generated receipt/revision and idempotency retention are documented.

Logs exclude keys and unnecessary private content. Per-bot/tenant limits prevent one producer exhausting storage or worker capacity. Error examples, retry examples, curl/Python quickstarts and contract fixtures are required deliverables, not completed by this draft.
