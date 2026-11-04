"""Regression checks for binding a notice to the exact release sources."""

import hashlib
from pathlib import Path
from typing import Any

import pytest

from scripts.crate_notices import check_commit
from tests.test_embedded_notices import archive_bytes


def test_publisher_commit_must_match_cached_crate(tmp_path: Path) -> None:
    raw = archive_bytes({"demo-1/.cargo_vcs_info.json": b'{"git":{"sha1":"wrong"}}'})
    with pytest.raises(ValueError, match="Source commit differs"):
        check_commit(
            raw, {}, {"name": "demo", "version": "1", "commit": "a" * 40}, tmp_path, False, {}
        )


@pytest.mark.parametrize("fault", [None, "missing file", "different upstream bytes", "wrong path"])
def test_older_crate_requires_all_published_rust_sources(tmp_path: Path, fault: str | None) -> None:
    files = {
        "Cargo.toml.orig": b'[package]\nname="demo"',
        "src/lib.rs": b"code",
        "tests/test.rs": b"test",
    }
    commit = "0" * 40
    row: dict[str, Any] = {"name": "demo", "version": "1", "commit": commit, "source_matches": []}
    for member, data in files.items():
        path = member.removesuffix(".orig")
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        row["source_matches"].append({"member": "demo-1/" + member, "path": path, "git_blob": blob})
        target = tmp_path / "supplement/example/demo" / commit / path
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_bytes(
            b"changed" if fault == "different upstream bytes" and member == "src/lib.rs" else data
        )
    if fault == "missing file":
        row["source_matches"].pop()
    elif fault == "wrong path":
        row["source_matches"][-1]["path"] = "elsewhere/test.rs"
    raw = archive_bytes({"demo-1/" + k: v for k, v in files.items()})
    crate = {"repository": "https://github.com/example/demo"}
    sources: dict[str, bytes] = {}
    if fault:
        with pytest.raises(ValueError):
            check_commit(raw, crate, row, tmp_path, False, sources)
    else:
        check_commit(raw, crate, row, tmp_path, False, sources)
        assert set(sources.values()) == set(files.values())
