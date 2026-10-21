"""Contract-boundary checks for untrusted preferences and routes."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from demo_model import channel_from_route, decode_preferences, encode_preferences


@pytest.mark.parametrize("raw", [None, "", "not json", "[]", "null", '{"version":999}', "x" * 4097])
def test_corrupt_or_incompatible_preferences_fall_back(raw):
    assert decode_preferences(raw) == (set(), "bars")


def test_unknown_sources_and_wrong_field_types_are_not_trusted():
    assert decode_preferences('{"version":1,"favorites":["shop","private",{},12],"chart_view":"script"}') == ({"shop"}, "bars")
    assert decode_preferences('{"version":1,"favorites":42,"chart_view":"values"}') == (set(), "values")


def test_preferences_round_trip_only_allowed_presentation_data():
    raw = encode_preferences({"shop", "secret-channel"}, "values")
    assert decode_preferences(raw) == ({"shop"}, "values")
    assert "secret-channel" not in raw


@pytest.mark.parametrize(("route", "expected"), [("/", None), ("/channels/news", "news"), ("/channels/shop?ignored=1", "shop"), ("/channels/private", "missing"), ("/channels/../../news", "missing")])
def test_routes_do_not_select_unknown_sources(route, expected):
    assert channel_from_route(route) == expected
