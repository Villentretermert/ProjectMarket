"""Call from your existing, owner-authorized Telegram handler; no Telegram credentials here."""

from marketob_bots.state import Journal
from marketob_sdk import BotClient


def publish_authorized_post(
    client: BotClient, journal: Journal, post_id: int, title: str, plain_text: str
) -> None:
    # The existing bot must authorize the source/chat before calling this adapter.
    journal.publish(
        client,
        "telegram_" + str(post_id),
        "news",
        {"title": title[:200], "body": plain_text[:10000]},
    )
