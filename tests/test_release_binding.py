"""Release evidence cannot silently follow a tag or hide changed installed bytes."""

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.delivery_bundle import ROOT
from scripts.release_binding import BASE, check_probes, compare, verify

BINDING = ROOT / "third_party/schema-20261109/binding.json"


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_collected_release_binding() -> None:
    value = verify(BINDING)
    assert value["component_occurrences"] == 584
    assert value["coverage_state"] == "partial"


@pytest.mark.parametrize("change", ["component", "notice", "gap", "role"])
def test_changed_inventory_requires_new_source_review(change: str) -> None:
    before = read(ROOT / BASE)
    after = read(ROOT / "third_party/schema-20261109/inventory.json")
    if change == "component":
        after["images"][0]["components"][0]["version"] = "unreviewed"
    elif change == "notice":
        after["images"][0]["shared_notices"] = []
    elif change == "gap":
        after["gaps"] = []
    else:
        after["images"][0]["role"] = after["images"][1]["role"]
    with pytest.raises(ValueError):
        compare(before, after)


@pytest.mark.parametrize("change", ["image", "native", "own", "launcher"])
def test_probe_cannot_hide_changed_installed_code(change: str) -> None:
    binding = read(BINDING)
    probe = binding["probes"]["api"]
    if change == "image":
        probe["image_id"] = "sha256:" + "0" * 64
    elif change == "native":
        probe["native"] = {}
    elif change == "own":
        files = probe["own"]["marketob-contracts"]["files"]
        files[next(iter(files))]["sha256"] = "0" * 64
    else:
        probe["own"]["marketob-contracts"]["generated_launchers"] = {"../unexpected": "0" * 64}
    with pytest.raises(ValueError):
        check_probes(binding)


def test_binding_cannot_report_false_component_count(tmp_path: Path) -> None:
    binding = read(BINDING)
    binding["component_occurrences"] = 1
    path = tmp_path / "binding.json"
    path.write_text(json.dumps(binding), encoding="utf-8")
    with pytest.raises(ValueError, match="Component count"):
        verify(path)
