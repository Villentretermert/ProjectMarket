"""Synthetic daily goods and deterministic request outcomes, never real purchases."""

from typing import Any

from marketob_sdk import APIError, BotClient, BotEvent, ProtocolError

from marketob_bots.common import Configuration, run
from marketob_bots.state import Journal

PRODUCTS: dict[str, dict[str, Any]] = {
    "soap": {
        "title": "Hand soap",
        "description": "Demo daily essential. Requests are simulated.",
        "price": {"amount_minor": 250, "currency": "EUR"},
        "availability": "in_stock",
    },
    "rice": {
        "title": "Rice, 1 kg",
        "description": "Demo pantry item. No payment or shipment.",
        "price": {"amount_minor": 320, "currency": "EUR"},
        "availability": "in_stock",
    },
    "paper_towels": {
        "title": "Paper towels",
        "description": "Demo item: the supplier will decline the request.",
        "price": {"amount_minor": 450, "currency": "EUR"},
        "availability": "in_stock",
    },
    "milk": {
        "title": "Milk, 1 litre",
        "description": "Demo unavailable item; requests are disabled.",
        "price": {"amount_minor": 180, "currency": "EUR"},
        "availability": "out_of_stock",
    },
}


def handle(client: BotClient, journal: Journal, event: BotEvent) -> None:
    journal.remember(event)
    try:
        acknowledgement = client.ack(event["event_id"])
    except APIError as error:
        if error.code == "request_cancelled":
            journal.finish(event["action_request_id"])
            return
        raise
    if acknowledgement["event_id"] != event["event_id"]:
        raise ProtocolError("ACK does not match the locally persisted event.")
    accepted = event["resource_id"] in {"soap", "rice"} and event["quantity"] == 1
    result = journal.demo_result(event, accepted)
    response = client.result(event["event_id"], result)
    if response["action_request_id"] != event["action_request_id"]:
        raise ProtocolError("Result response does not match the local request.")
    journal.finish(event["action_request_id"])


def cycle(client: BotClient, journal: Journal, config: Configuration) -> dict[str, int]:
    for resource, payload in PRODUCTS.items():
        journal.publish(client, resource, "product", payload)
    handled = 0
    # Local pending includes ACKed work and results accepted just before a process crash.
    for event in journal.pending():
        handle(client, journal, event)
        handled += 1
    cursor = None
    while True:
        page = client.events(cursor=cursor)
        for event in page["items"]:
            handle(client, journal, event)
            handled += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
    # Missing local history is never reconstructed by repeating external effects.
    remaining = client.requests(limit=100)
    return {
        "products": len(PRODUCTS),
        "handled": handled,
        "unresolved_in_first_page": len(remaining["items"]),
    }


def main() -> None:
    run("catalog", cycle, 2.5)


if __name__ == "__main__":
    main()
