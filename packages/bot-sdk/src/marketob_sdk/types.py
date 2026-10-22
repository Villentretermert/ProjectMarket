"""Public response shapes; validated against the shared schema before return."""

from typing import Literal, TypedDict


class Receipt(TypedDict):
    message_id: str
    receipt_id: str
    data_revision: int
    received_at: str


class BotEvent(TypedDict):
    event_id: str
    action_request_id: str
    actor_ref: str
    channel_id: str
    resource_id: str
    action_id: str
    quantity: int
    observed_source_revision: int
    created_at: str


class EventPage(TypedDict):
    items: list[BotEvent]
    next_cursor: str | None


class ActionRequest(TypedDict):
    action_request_id: str
    channel_id: str
    resource_id: str
    action_id: str
    state: Literal["queued", "processing", "confirmed", "failed", "unknown", "cancelled"]
    created_at: str
    updated_at: str
    summary: str
