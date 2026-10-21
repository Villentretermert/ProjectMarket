# Bot developer quickstart — contract only

This walkthrough targets the **future** local server at `http://127.0.0.1:8000`; PM-004 does not start that server. Use HTTPS remotely. The bot is any HTTP process, including a Telegram adapter. It has no database access. Values below are placeholders, not working credentials.

1. Owner signs in locally, creates a bot in Studio (`POST /v1/bots`) and creates its draft channel (`POST /v1/channels`). Copy the returned channel ID into the bot configuration. Keep the one-time registration credential out of source control, browser storage, command histories and chat.
2. Bot sends `POST /v1/bot-registrations/exchange` with JSON `{}` and the registration credential as bearer authorization. Securely store the returned operational `api_key`. Do not print the entire response. Lost response: ask the owner to issue a fresh operational key; the consumed registration credential cannot be replayed.
3. Send [the valid product message](../../contracts/examples/product-message.json) to `POST /v1/bot/messages` using the operational bearer key. Change the example channel ID to your assigned channel and keep message ID/revision stable when retrying. Example:

```python
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

# The local process reads its own key from configuration, never from a UI template.
body = json.loads(Path('contracts/examples/product-message.json').read_text())
body['channel_id'] = os.environ['MARKETOB_CHANNEL_ID']
request = Request(
    'http://127.0.0.1:8000/v1/bot/messages',
    data=json.dumps(body).encode('utf-8'), method='POST',
    headers={'Authorization': 'Bearer ' + os.environ['MARKETOB_BOT_KEY'],
             'Content-Type': 'application/json'},
)
with urlopen(request, timeout=10) as response:
    receipt = json.load(response)
print(receipt['receipt_id'])  # Log the receipt ID, never credentials/payloads.
```

4. Owner replaces the channel draft with a product block bound to `item_notebook`, action `buy_notebook` of kind `request_purchase`, matching resource ID and English label `Send request`. The draft uses schema1.0 and the next template version. Publish that validated version. Consumers can read `GET /v1/channels/{slug}`; selected-member channels require a current session/grant.
5. Consumer sends `POST /v1/channels/{channel_id}/actions`, session cookie, `X-CSRF-Token`, `Idempotency-Key: request-demo-001`, and:

```json
{"action_id":"buy_notebook","resource_id":"item_notebook","observed_source_revision":1,"quantity":1}
```

HTTP202 creates a **request**, not a payment. Store the returned `action_request_id`. An ambiguous network failure retries the same body/key; a stale resource error refreshes the source and requires the user's new decision.

6. Bot polls `GET /v1/bot/events?limit=100&wait=25` with its operational key. For each event: persist event/request identity in its own durable inbox, then POST `{}` to `/v1/bot/events/{event_id}/ack`. Only after a successful ACK may it execute the side effect. Use action_request_id as the external service idempotency key. On restart consult the durable inbox and `GET /v1/bot/requests` before doing work again.
7. Send result (HTTP200 is transport acceptance of this business result):

```json
{"result_id":"result-demo-001","result_revision":1,"state":"confirmed","summary":"Your request was accepted. No payment has been taken."}
```

Endpoint: `POST /v1/bot/events/{event_id}/result`. In real integrations, report confirmed **only after the bot has evidence of its business outcome**. A queued or ACKed event is not that evidence. Use processing while executing; report failed only for known failure. Preserve uncertainty and reconcile ambiguous effects.

8. Consumer reads `GET /v1/action-requests/{action_request_id}` and foreground update hints. It shows confirmed/failed only from authoritative status. It can add this block to My Space and share layout references, which never contain this request or the bot key.

GET scan pseudocode:

```text
repeat while running:
    cursor = absent
    repeat:
        page = GET events(cursor, limit=100, wait=25 only if cursor absent)
        for event in page.items:
            durable_deduplicated_inbox(event)
            ACK(event.id)
            reconcile_or_execute_once(event.action_request_id)
            POST stable_result_if_known(event.id)
        cursor = page.next_cursor
    until cursor is null
    # Start a NEW scan. Do not keep the final cursor as an offset.
```

Use bounded retry/backoff for429/503 and network errors. For410 discard cursor and restart; unACKed events are still pending. Do not automatically repeat an external effect when an ACK/result response is lost. See [the normative protocol](PROTOCOL.md) for all limits, error codes, revocation races and retention rules. The Python SDK and two real pilot bots are PM-011.
