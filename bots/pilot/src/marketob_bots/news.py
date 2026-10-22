"""Bounded public RSS/Atom headlines and a chart of the retrieved feed window."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from http.client import HTTPException
from importlib.resources import files
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]
from defusedxml.ElementTree import fromstring  # type: ignore[import-untyped]
from marketob_sdk import BotClient
from marketob_sdk.client import NoRedirect

from marketob_bots.common import RSS_URL, Configuration, FeedError, run
from marketob_bots.state import Journal


class PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain(value: str) -> str:
    parser = PlainText()
    parser.feed(value)
    return " ".join("".join(parser.parts).replace("\x00", "").split())


def safe_link(value: str) -> str:
    try:
        url = urlsplit(value)
        if (
            url.scheme in {"http", "https"}
            and url.hostname
            and url.username is None
            and url.password is None
            and len(value) <= 2048
        ):
            return value
    except ValueError:
        pass
    return ""


@dataclass(frozen=True)
class FeedItem:
    title: str
    link: str
    published: datetime | None


def parse_feed(raw: bytes) -> list[FeedItem]:
    if len(raw) > 1048576:
        raise FeedError("RSS feed exceeds the 1 MiB limit; previous data is preserved.")
    try:
        root = fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except ParseError, DefusedXmlException, ValueError:
        raise FeedError("RSS feed is invalid or uses unsupported XML features.") from None
    if root.tag == "rss":
        nodes = root.findall("./channel/item")
        namespace = ""
    elif root.tag == "{http://www.w3.org/2005/Atom}feed":
        nodes = root.findall("{http://www.w3.org/2005/Atom}entry")
        namespace = "{http://www.w3.org/2005/Atom}"
    else:
        raise FeedError("Use an RSS 2.0 or Atom 1.0 feed.")
    items = []
    for node in nodes[:100]:
        title = plain(node.findtext(namespace + "title", ""))[:200]
        if not title:
            continue
        link = (
            node.findtext("link", "")
            if not namespace
            else next(
                (
                    n.get("href", "")
                    for n in node.findall(namespace + "link")
                    if n.get("rel", "alternate") == "alternate"
                ),
                "",
            )
        )
        date = (
            node.findtext("pubDate", "")
            if not namespace
            else node.findtext(namespace + "published", node.findtext(namespace + "updated", ""))
        )
        published = None
        try:
            parsed = (
                datetime.fromisoformat(date.replace("Z", "+00:00"))
                if namespace
                else parsedate_to_datetime(date)
            )
            if parsed.tzinfo is not None:
                published = parsed.astimezone(UTC)
        except ValueError, TypeError, OverflowError:
            pass
        items.append(FeedItem(title, safe_link(link.strip()), published))
    if not items:
        raise FeedError("RSS feed has no valid titled entries; previous data is preserved.")
    return items


def fetch_feed(url: str) -> bytes:
    try:
        parsed = urlsplit(url)
        if (
            not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or (
                parsed.scheme != "https"
                and not (
                    parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                )
            )
        ):
            raise FeedError("RSS requires HTTPS, except loopback test fixtures.")
        request = Request(
            url,
            headers={
                "User-Agent": "MarkeTOB-Pilot/0.1",
                "Accept": "application/rss+xml, application/atom+xml, application/xml",
            },
        )
        # This opener has no platform Authorization header and does not follow redirects.
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            if response.headers.get("Content-Encoding", "identity") != "identity":
                raise FeedError("Compressed RSS is unsupported; use a plain XML feed.")
            raw = response.read(1048577)
        if len(raw) > 1048576:
            raise FeedError("RSS feed exceeds the 1 MiB limit.")
        return bytes(raw)
    except URLError, HTTPException, OSError, ValueError:
        raise FeedError(
            "RSS fetch failed; previous data is preserved. Check the configured final HTTPS URL."
        ) from None


def cycle(client: BotClient, journal: Journal, config: Configuration) -> dict[str, int]:
    journal.flush_pending(client)
    raw = (
        files("marketob_bots").joinpath("fixtures/rss.xml").read_bytes()
        if config.offline
        else fetch_feed(config.rss_url)
    )
    items = parse_feed(raw)
    source = (
        "Synthetic RSS fixture"
        if config.offline
        else "BBC News · https://www.bbc.com/news"
        if config.rss_url == RSS_URL
        else "Configured RSS feed"
    )
    for index in range(5):
        if index < len(items):
            item = items[index]
            body = "Source: " + source
            if item.published:
                body += "\nPublished: " + item.published.isoformat()
            if item.link:
                body += "\nRead the full story: " + item.link
            payload = {"title": item.title, "body": body}
        else:
            payload = {
                "title": "No additional feed entry",
                "body": "This feed currently has fewer than five titled entries.",
            }
        journal.publish(client, "news_" + str(index + 1), "news", payload)
    counts = Counter(
        int(item.published.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        for item in items
        if item.published
    )
    points = [{"x": stamp, "y": count} for stamp, count in sorted(counts.items())]
    chart: dict[str, Any] = {
        "title": "Dated entries in the current feed window",
        "x_label": "Publication day (UTC)",
        "x_kind": "time" if counts else "number",
        "y_label": "Entries",
        "unit": "entries",
        "series": [{"name": "Known publication dates", "points": points or [{"x": 0, "y": 0}]}],
    }
    if not counts:
        chart.update(title="No publication dates available", x_label="Feed window")
    journal.publish(client, "feed_activity", "chart", chart)
    return {"feed_entries": len(items), "news_blocks": 5, "dated_entries": sum(counts.values())}


def main() -> None:
    run("news", cycle, 300)


if __name__ == "__main__":
    main()
