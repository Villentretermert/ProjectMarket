"""Cheap worker probe: read its successful-pass heartbeat using only the stdlib."""

import tempfile
import time
from pathlib import Path

HEARTBEAT = Path(tempfile.gettempdir()) / "marketob-maintenance-heartbeat"


def healthy(path: Path = HEARTBEAT, *, now: float | None = None) -> bool:
    try:
        age = (time.time() if now is None else now) - path.stat().st_mtime
    except OSError:
        return False
    return 0 <= age <= 130


if __name__ == "__main__":
    raise SystemExit(0 if healthy() else 1)
