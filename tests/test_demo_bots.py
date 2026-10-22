"""Bot-owned durable journals and RSS parsing; no platform database imports."""

from importlib.resources import files
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from marketob_bots.catalog import handle
from marketob_bots.common import Configuration, FeedError, configuration
from marketob_bots.news import cycle, parse_feed
from marketob_bots.state import Journal, StateError
from marketob_sdk import APIError, BotClient, BotEvent, TransportError

EVENT: BotEvent = {
    "event_id": "event_one",
    "action_request_id": "request_one",
    "actor_ref": "actor_one",
    "channel_id": "ch_one",
    "resource_id": "soap",
    "action_id": "request_soap",
    "quantity": 1,
    "observed_source_revision": 1,
    "created_at": "2026-10-22T00:00:00Z",
}


def accepting_client() -> Any:
    client = Mock(spec=BotClient)
    client.send_message.side_effect = lambda body: {
        "message_id": body["message_id"],
        "receipt_id": "receipt",
        "data_revision": 1,
        "received_at": "2026-10-22T00:00:00Z",
    }
    client.ack.return_value = {"event_id": "event_one", "acknowledged_at": "2026-10-22T00:00:00Z"}
    client.result.return_value = {"action_request_id": "request_one", "state": "confirmed"}
    return client


def test_outbound_crash_replays_original_message_then_advances_revision(tmp_path: Path) -> None:
    path = tmp_path / "bot.sqlite3"
    client = accepting_client()
    client.send_message.side_effect = TransportError("Synthetic lost response")
    journal = Journal(path, "bot_one", "ch_one")
    with pytest.raises(TransportError):
        journal.publish(client, "news", "news", {"title": "First", "body": "Demo"})
    original = client.send_message.call_args.args[0]
    journal.close()
    restarted = Journal(path, "bot_one", "ch_one")
    success = accepting_client()
    restarted.publish(success, "news", "news", {"title": "First", "body": "Demo"})
    assert success.send_message.call_args.args[0] == original
    restarted.publish(success, "news", "news", {"title": "Second", "body": "Demo"})
    latest = success.send_message.call_args.args[0]
    assert latest["source_revision"] == 2 and latest["message_id"] != original["message_id"]
    restarted.close()
    with pytest.raises(StateError):
        Journal(path, "bot_another", "ch_one")


def test_inbox_precedes_ack_and_terminal_effect_survives_result_response_loss(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.sqlite3"
    journal = Journal(path, "bot_one", "ch_one")
    client = accepting_client()

    def ack(_event: str) -> dict[str, str]:
        assert journal.db.execute("SELECT count(*) FROM inbox").fetchone()[0] == 1
        return {"event_id": "event_one", "acknowledged_at": "2026-10-22T00:00:00Z"}

    client.ack.side_effect = ack
    client.result.side_effect = TransportError("Synthetic lost terminal response")
    with pytest.raises(TransportError):
        handle(client, journal, EVENT)
    first = client.result.call_args.args[1]
    assert journal.db.execute("SELECT count(*) FROM demo_effects").fetchone()[0] == 1
    journal.close()
    restarted = Journal(path, "bot_one", "ch_one")
    success = accepting_client()
    handle(success, restarted, restarted.pending()[0])
    assert success.result.call_args.args[1] == first
    assert restarted.db.execute("SELECT count(*) FROM demo_effects").fetchone()[0] == 1
    assert restarted.pending() == []
    restarted.close()


def test_cancelled_ack_never_creates_demo_effect(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "cancelled.sqlite3", "bot_one", "ch_one")
    client = accepting_client()
    client.ack.side_effect = APIError(409, "request_cancelled")
    handle(client, journal, EVENT)
    assert journal.db.execute("SELECT count(*) FROM demo_effects").fetchone()[0] == 0
    client.result.assert_not_called()
    assert journal.pending() == []
    journal.close()


def test_rss_fixture_is_deterministic_and_does_not_republish_unchanged_data(tmp_path: Path) -> None:
    raw = files("marketob_bots").joinpath("fixtures/rss.xml").read_bytes()
    assert len(parse_feed(raw)) == 5
    config = Configuration(
        "http://127.0.0.1:8000", "ch_one", tmp_path / "news.sqlite3", "synthetic", offline=True
    )
    client = accepting_client()
    journal = Journal(config.state_path, "bot_one", "ch_one")
    assert cycle(client, journal, config) == {
        "feed_entries": 5,
        "news_blocks": 5,
        "dated_entries": 5,
    }
    assert client.send_message.call_count == 6
    chart = client.send_message.call_args.args[0]["payload"]
    assert [p["y"] for p in chart["series"][0]["points"]] == [1, 2, 2]
    cycle(client, journal, config)
    assert client.send_message.call_count == 6
    journal.close()


@pytest.mark.parametrize(
    "payload",
    [
        b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///secret">]><rss><channel><item><title>&x;</title></item></channel></rss>',
        b"<rss><channel/></rss>",
        b"<html>wrong</html>",
        b"invalid",
        b"x" * 1048577,
    ],
    ids=["external_entity", "empty", "wrong_root", "invalid", "oversized"],
)
def test_unusable_feed_is_rejected_without_external_entity_fetch(payload: bytes) -> None:
    with pytest.raises(FeedError):
        parse_feed(payload)


def test_atom_and_unsafe_links_are_plain_text() -> None:
    items = parse_feed(
        b'<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        b'<title>&lt;b&gt;Demo&lt;/b&gt;</title><link href="javascript:alert(1)"/>'
        b"<updated>2026-10-22T12:00:00Z</updated></entry></feed>"
    )
    assert items[0].title == "Demo" and items[0].link == ""
    assert items[0].published is not None


def test_bot_configuration_rejects_platform_database_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MARKETOB_DATABASE_URL", "postgresql://synthetic:secret@example.invalid/db")
    with pytest.raises(StateError, match="Do not pass platform database") as error:
        configuration("catalog", None)
    assert "secret" not in str(error.value)
