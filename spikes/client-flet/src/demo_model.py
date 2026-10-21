"""Public fixture model for comparing client stacks, never authentication."""

import json
from urllib.parse import urlsplit

SCHEMA_VERSION = 1
CHANNELS = {
    "shop": {"title": "Northstar Shop", "description": "Products from your catalog bot"},
    "news": {"title": "Daily Brief", "description": "Selected updates from your news bot"},
}
NEWS = [
    {"id": "news-1", "title": "Your sources, one familiar home", "body": "Organize updates from independent bots in a single workspace."},
    {"id": "news-2", "title": "Choose how your data looks", "body": "Keep the source while changing compatible visualizations."},
]
PRODUCT = {"id": "notebook", "title": "Daily notebook", "amount_minor": 1800, "currency": "EUR", "description": "A5 notebook with dotted pages."}
VIEWS = [42, 55, 51, 68, 72, 65, 84]


def channel_from_route(route: str) -> str | None:
    """Only known channels are routable; unknown routes show a real empty state."""
    path = urlsplit(route).path.strip("/")
    if not path:
        return None
    parts = path.split("/")
    return parts[1] if len(parts) == 2 and parts[0] == "channels" and parts[1] in CHANNELS else "missing"


def encode_preferences(favorites: set[str], chart_view: str) -> str:
    # Persist presentation preferences, never tokens or private bot payloads.
    return json.dumps({"version": SCHEMA_VERSION, "favorites": sorted(favorites & CHANNELS.keys()), "chart_view": chart_view if chart_view in {"bars", "values"} else "bars"})


def decode_preferences(raw: object) -> tuple[set[str], str]:
    if not isinstance(raw, str) or len(raw) > 4096:
        return set(), "bars"
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return set(), "bars"
    if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
        return set(), "bars"
    candidates = data.get("favorites", [])
    favorites = {item for item in candidates if isinstance(item, str) and item in CHANNELS} if isinstance(candidates, list) else set()
    chart = data.get("chart_view")
    return favorites, chart if chart in {"bars", "values"} else "bars"
