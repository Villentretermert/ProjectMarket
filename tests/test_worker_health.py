"""Probe failure semantics and isolation from the full application's import cost."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from marketob_api.worker_health import healthy


@pytest.mark.parametrize("age,expected", [(-1, False), (0, True), (130, True), (131, False)])
def test_heartbeat_freshness(tmp_path: Path, age: float, expected: bool) -> None:
    heartbeat = tmp_path / "heartbeat"
    assert not healthy(heartbeat, now=1000)
    heartbeat.touch()
    os.utime(heartbeat, (1000 - age, 1000 - age))
    assert healthy(heartbeat, now=1000) is expected


def test_probe_does_not_import_api_or_compile_schemas() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import marketob_api.maintenance; "
            "assert not {'fastapi','psycopg','jsonschema','jsonschema_rs'} & sys.modules.keys()",
        ],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0
