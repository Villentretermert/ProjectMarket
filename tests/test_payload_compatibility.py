"""Compiled hot-path validator must preserve the canonical schema's accepted language."""

import json
from copy import deepcopy
from importlib.resources import files
from typing import Any

from marketob_api.payloads import MESSAGE_VALIDATOR, VALIDATORS


def test_compiled_message_schema_matches_reference_cases_and_boundary_mutations() -> None:
    root = files("contracts").joinpath("examples")
    cases = json.loads(root.joinpath("cases.json").read_text(encoding="utf-8"))
    values: list[dict[str, Any]] = [c["value"] for c in cases if c["schema"] == "Message"]
    chart = json.loads(root.joinpath("chart-message.json").read_text(encoding="utf-8"))
    for name in ("news", "product", "chart"):
        example = json.loads(root.joinpath(name + "-message.json").read_text(encoding="utf-8"))
        values.append(example)
        for key in example:
            missing = deepcopy(example)
            del missing[key]
            values.append(missing)
        for revision in (0, -1, True, 1.0, "1", None, 2**53, 2**63):
            values.append({**example, "source_revision": revision})
        for occurred in (
            "wrong",
            "2026-10-23",
            "2026-10-23T00:00:00Z",
            "2026-10-23T00:00:00+02:00",
        ):
            values.append({**example, "occurred_at": occurred})
        values.append({**example, "unknown_field": "must reject"})
    for number in (None, True, "5", -3, 0, 0.25, 1e100):
        changed = deepcopy(chart)
        changed["payload"]["series"][0]["points"][0]["y"] = number
        values.append(changed)
    for length in (0, 1, 1000, 1001):
        changed = deepcopy(chart)
        changed["payload"]["series"][0]["points"] = [{"x": n, "y": n} for n in range(length)]
        values.append(changed)
    for value in values:
        assert MESSAGE_VALIDATOR.is_valid(value) == VALIDATORS["Message"].is_valid(value)
