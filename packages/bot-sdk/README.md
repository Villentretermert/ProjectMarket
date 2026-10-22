# MarkeTOB Python bot SDK

Python 3.14, contract 1.0 / revision 1.0.3. From the repository root run `uv sync --locked`.
The SDK is a workspace package, not yet published to PyPI. Bot processes need only
`marketob-bot-sdk` and the bundled schemas; they never import the API or connect to PostgreSQL.

## Registration and first message

An authenticated B2B owner creates a bot with `POST /v1/bots` and a channel with
`POST /v1/channels`. See [owner API](../../docs/api/BOTS.md) and
[channels](../../docs/api/CHANNELS.md). The one-time registration credential expires
after 15 minutes. Exchange it once in a private process:

```python
import os
from marketob_sdk import BotClient

origin = os.environ['MARKETOB_API_URL']
issued = BotClient(origin).exchange_registration(os.environ['MARKETOB_REGISTRATION_KEY'])
# Store issued['api_key'] in a private secret store, never in logs or source control.
# Set MARKETOB_BOT_KEY for this bot only, then remove the registration credential.
```

The operational key expires after 90 days. Revoke/rotate through the owner API.
If the exchange response is lost, the SDK does not repeat this one-time operation;
the owner must issue a new operational key. Other ambiguous writes are retried
with exactly the same serialized body and identifier.

```python
import os
from datetime import UTC, datetime
from marketob_sdk import BotClient

client = BotClient(os.environ['MARKETOB_API_URL'], os.environ['MARKETOB_BOT_KEY'])
message = {
    'schema_version': '1.0', 'message_id': 'first_news_v1',
    'channel_id': os.environ['MARKETOB_CHANNEL_ID'], 'resource_id': 'first_news',
    'source_revision': 1, 'occurred_at': datetime.now(UTC).isoformat(),
    'kind': 'data', 'content_type': 'news',
    'payload': {'title': 'Hello MarkeTOB', 'body': 'My first bot message.'},
}
# Persist the complete message before sending. Reuse it unchanged after uncertainty.
receipt = client.send_message(message)
```

The example is a single publication; regenerating `occurred_at` while retaining
`message_id` creates a conflict. For durable repeated updates, use the sample
`marketob_bots.state.Journal` implementation, which persists the envelope before HTTP.
Use a single writer and a monotonically increasing revision per channel/resource.
Sharing keys or losing revision state is not a recovery strategy.

## Requests, ACK and results

`client.events(limit=100, wait=25)` reads unACKed events. Follow `next_cursor` with
`wait=0`; finish a scan within its 60-second cursor lifetime. `client.requests()`
lists all unresolved requests, including ACKed ones. GET has no delivery side effect.

For each event: persist its whole body locally, commit, then call
`client.ack(event['event_id'])`. ACK means durable receipt, not purchase confirmation.
Execute an idempotent business operation keyed by `action_request_id`, persist
its outcome and stable `result_id`, then call:

```python
result = {
    'result_id': 'stored_result_id', 'result_revision': 1,
    'state': 'confirmed', 'summary': 'Request confirmed. No payment was taken.',
}
status = client.result(event['event_id'], result)
```

Use `failed` for a declined request, `processing` for nonterminal progress. Repeat
the same result after a lost response; never generate a new purchase on redelivery.
The sample catalog implements this ordering and a transactional **synthetic**
effect ledger. Real payment/order integrations need their own durable idempotency
contract; the SDK does not promise exactly-once external effects. Restore a missing
bot journal from backup before resolving ACKed work; do not guess whether it ran.

## Transport and errors

- HTTPS origins outside loopback; TLS verification stays enabled. No redirects.
  Only the explicit Compose opt-in permits `http://api:8000`.
- Request/response validation uses the bundled closed JSON schemas. Request limit
  256 KiB, response limit 512 KiB. Keys and remote error bodies are omitted from errors.
- `APIError`: `status`, allowlisted `code`, optional numeric `retry_after`.
  Retry 429/503 and transport failures up to four attempts by default, with backoff
  and jitter. Retry-After above 60 seconds is returned to the caller without sleeping.
- `TransportError`: response may be lost; recover the persisted identity.
  `ProtocolError`: fix invalid input or incompatible server response; do not retry blindly.
- 401/403 requires credential/scope repair; 409 requires reconciliation. No automatic
  retries for these statuses. Default timeout 35 seconds supports long polling up to 25 seconds.

Full [protocol](../../docs/api/PROTOCOL.md), [actions](../../docs/api/ACTIONS.md),
[runnable pilot](../../docs/setup/PILOT_BOTS.md), and
[Telegram adapter](../../bots/examples/telegram_adapter.py).
