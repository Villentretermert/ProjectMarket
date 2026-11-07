"""Controls for the recipient replacement recipe and its proof conditions."""

import copy
import io
import tarfile
from pathlib import Path
from typing import Any

import pytest

from scripts.replace_psycopg import MARKER, PATCH, compare, prepare, sha256


def source_archive(extra: tarfile.TarInfo | None = None) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name in ("psycopg_c/_psycopg.c", "psycopg_c/pq.c", "LICENSE.txt"):
            info = tarfile.TarInfo("psycopg_c-3.3.6/" + name)
            data = b"original bytes\n"
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        if extra:
            archive.addfile(extra)
    return stream.getvalue()


def test_source_rejects_wrong_hash_without_creating_tree(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        prepare(source_archive(), "0" * 64, tmp_path / "context")
    assert not (tmp_path / "context").exists()


@pytest.mark.parametrize("name", ["../escape", "/escape", "psycopg_c-3.3.6/../../escape"])
def test_source_rejects_path_escape(tmp_path: Path, name: str) -> None:
    data = source_archive(tarfile.TarInfo(name))
    with pytest.raises(ValueError, match="member"):
        prepare(data, sha256(data), tmp_path / "context")
    assert not (tmp_path / "escape").exists()


def test_source_rejects_links(tmp_path: Path) -> None:
    info = tarfile.TarInfo("psycopg_c-3.3.6/link")
    info.type = tarfile.SYMTYPE
    info.linkname = "/etc/passwd"
    data = source_archive(info)
    with pytest.raises(ValueError, match="member"):
        prepare(data, sha256(data), tmp_path / "context")


def test_source_records_two_c_changes_and_keeps_license(tmp_path: Path) -> None:
    data = source_archive()
    result = prepare(data, sha256(data), tmp_path / "context")
    assert len(result["changes"]) == 2
    for change in result["changes"]:
        actual = (tmp_path / "context/source" / change["path"]).read_bytes()
        assert actual == b"original bytes\n" + PATCH.encode()
        assert change["before"] != change["after"] == sha256(actual)
    assert (tmp_path / "context/source/LICENSE.txt").read_bytes() == b"original bytes\n"
    with pytest.raises(FileExistsError):
        prepare(data, sha256(data), tmp_path / "context")


def inventories() -> tuple[dict[str, Any], dict[str, Any]]:
    before: dict[str, Any] = {
        "implementation": "c",
        "driver_version": "3.3.6",
        "extension_version": "3.3.6",
        "libpq": 180006,
        "libpq_build": 180006,
        "uid": 10001,
        "other_site_packages_sha256": "other",
        "system_packages_sha256": "system",
        "extensions": [
            {"name": name, "sha256": "old-" + name, "marker": None}
            for name in ("_psycopg.so", "pq.so")
        ],
    }
    after = copy.deepcopy(before)
    for extension in after["extensions"]:
        extension.update(sha256="new-" + extension["name"], marker=MARKER.decode())
    return before, after


def test_valid_replacement() -> None:
    compare(*inventories())


@pytest.mark.parametrize("failure", ["unmodified", "missing_marker", "other_package", "root"])
def test_false_replacement_proof_rejected(failure: str) -> None:
    before, after = inventories()
    if failure == "unmodified":
        after["extensions"][0]["sha256"] = before["extensions"][0]["sha256"]
    elif failure == "missing_marker":
        after["extensions"][1]["marker"] = None
    elif failure == "other_package":
        after["other_site_packages_sha256"] = "changed"
    else:
        after["uid"] = 0
    with pytest.raises(ValueError):
        compare(before, after)
