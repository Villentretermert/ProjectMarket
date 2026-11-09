"""Synthetic publisher-shaped RSS exercises the real parser and durable journal."""

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from marketob_bots.common import RSS_URL, Configuration, FeedError
from marketob_bots.news import cycle, parse_feed
from marketob_bots.state import Journal
from marketob_sdk import BotClient

FIXTURE = Path(__file__).parent / "fixtures" / "meduza-shaped.xml"


def test_publisher_fields_are_reduced_to_plain_headline_date_and_link() -> None:
    items = parse_feed(FIXTURE.read_bytes())
    assert len(items) == 6
    assert items[0].title == "Демо: новости & события"
    assert items[0].link == "https://example.invalid/news/demo-one"
    assert items[0].published is not None
    assert items[0].published.isoformat() == "2026-11-09T00:30:00+00:00"
    assert items[1].published is not None
    assert items[1].published.isoformat() == "2026-11-09T01:00:00+00:00"
    assert [item.link for item in items[2:4]] == ["", ""]
    assert [item.published for item in items[2:5]] == [None, None, None]


@pytest.mark.parametrize(
    ("url", "source"),
    [
        (RSS_URL, "Meduza · https://meduza.io"),
        ("https://meduza.io/rss/en/all", "Meduza (English) · https://meduza.io/en"),
        ("https://feeds.bbci.co.uk/news/world/rss.xml", "BBC News · https://www.bbc.com/news"),
        ("https://example.invalid/rss", "Configured RSS feed"),
    ],
    ids=["meduza_ru", "meduza_en", "legacy_bbc", "custom"],
)
def test_source_publication_replay_and_failure_preserve_existing_slots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, url: str, source: str
) -> None:
    assert RSS_URL == "https://meduza.io/rss/all"
    feed = Mock(return_value=FIXTURE.read_bytes())
    monkeypatch.setattr("marketob_bots.news.fetch_feed", feed)
    config = Configuration(
        "http://127.0.0.1:8000", "ch_one", tmp_path / "news.sqlite3", "synthetic", rss_url=url
    )
    client: Any = Mock(spec=BotClient)
    client.send_message.side_effect = lambda body: {"message_id": body["message_id"]}
    journal = Journal(config.state_path, "bot_one", "ch_one")
    try:
        # A source switch updates the five existing slots, retaining My Space references.
        for index in range(1, 6):
            journal.publish(client, f"news_{index}", "news", {"title": "Before", "body": "Demo"})
        client.reset_mock()
        assert cycle(client, journal, config) == {
            "feed_entries": 6,
            "news_blocks": 5,
            "dated_entries": 3,
        }
        feed.assert_called_once_with(url)
        messages = [call.args[0] for call in client.send_message.call_args_list]
        assert [m["resource_id"] for m in messages] == [
            "news_1",
            "news_2",
            "news_3",
            "news_4",
            "news_5",
            "feed_activity",
        ]
        assert all(m["source_revision"] == 2 for m in messages[:5])
        assert all(m["payload"]["body"].startswith("Source: " + source) for m in messages[:5])
        assert "Published: 2026-11-09T00:30:00+00:00" in messages[0]["payload"]["body"]
        assert (
            "Read the full story: https://example.invalid/news/demo-one"
            in messages[0]["payload"]["body"]
        )
        assert all("Published:" not in m["payload"]["body"] for m in messages[2:5])
        assert all("Read the full story:" not in m["payload"]["body"] for m in messages[2:4])
        assert [p["y"] for p in messages[-1]["payload"]["series"][0]["points"]] == [1, 2]
        assert not any(
            token in str(messages)
            for token in ("ARTICLE_MUST_NOT_COPY", "image.jpg", "tracker", "<b>")
        )
        journal.close()
        journal = Journal(config.state_path, "bot_one", "ch_one")
        client.reset_mock()
        cycle(client, journal, config)
        client.send_message.assert_not_called()
        before = journal.db.execute("SELECT * FROM outbound ORDER BY resource_id").fetchall()
        for failure in (
            FeedError("Synthetic unavailable feed"),
            b"invalid XML",
            b"<rss><channel/></rss>",
        ):
            if isinstance(failure, FeedError):
                feed.side_effect = failure
            else:
                feed.side_effect = None
                feed.return_value = failure
            with pytest.raises(FeedError):
                cycle(client, journal, config)
            client.send_message.assert_not_called()
            assert (
                journal.db.execute("SELECT * FROM outbound ORDER BY resource_id").fetchall()
                == before
            )
    finally:
        journal.close()
