"""Regression checks for exact Debian revisions, descriptor closure and kit integrity."""

import io
import json
import lzma
import tarfile
from pathlib import Path
from typing import Any

import pytest

from scripts.collect_notices import digest
from scripts.debian_sources import (
    check_coverage,
    check_descriptor,
    check_index,
    obtain,
    verify_archive,
)


def source_row() -> dict[str, Any]:
    return {
        "package": "demo",
        "version": "1:1.0-2",
        "directory": "pool/main/d/demo",
        "index": "main",
        "files": [
            {"name": name, "size": 7, "sha256": digest(name.encode())}
            for name in ["demo_1.0-2.dsc", "demo_1.0.orig.tar.gz", "demo_1.0-2.debian.tar.xz"]
        ],
    }


def paragraph(row: dict[str, Any], field: str, files: list[dict[str, Any]]) -> bytes:
    header = (
        f"{field}: {row['package']}\nVersion: {row['version']}\nDirectory: {row['directory']}\n"
    )
    return (
        header
        + "Checksums-Sha256:\n"
        + "".join(f" {f['sha256']} {f['size']} {f['name']}\n" for f in files)
    ).encode()


def test_index_and_descriptor_preserve_epoch_and_patch() -> None:
    row = source_row()
    data = lzma.compress(paragraph(row, "Package", row["files"]))
    check_index(data, "Sources.xz", [row])
    check_descriptor(paragraph(row, "Source", row["files"][1:]), row)
    with pytest.raises(ValueError, match="absent"):
        check_index(data, "Sources.xz", [{**row, "version": "1.0-2"}])
    with pytest.raises(ValueError, match="file set"):
        check_descriptor(paragraph(row, "Source", row["files"][1:2]), row)


def test_coverage_preserves_both_revisions_across_images() -> None:
    installed = [
        {"ecosystem": "deb", "source_package": "demo", "source_version": v} for v in ["1", "2"]
    ]
    inventory = json.dumps({"images": [{"components": [r]} for r in installed]}).encode()
    plan: dict[str, Any] = {
        "inventory_sha256": digest(inventory),
        "indexes": {"main": {}},
        "packages": [{**source_row(), "version": v} for v in ["1", "2"]],
    }
    check_coverage(inventory, plan)
    plan["packages"] = [plan["packages"][0]] * 2
    with pytest.raises(ValueError, match="coverage"):
        check_coverage(inventory, plan)


@pytest.mark.parametrize("fault", ["missing", "corrupt", "duplicate", "link"])
def test_archive_verification_rejects_damaged_delivery(tmp_path: Path, fault: str) -> None:
    kit = tmp_path / "kit.tar"
    with tarfile.open(kit, "w") as archive:
        for _ in range(0 if fault == "missing" else 2 if fault == "duplicate" else 1):
            member = tarfile.TarInfo("pool/source")
            data = b"other" if fault == "corrupt" else b"input"
            member.size = len(data)
            if fault == "link":
                member.type = tarfile.SYMTYPE
                member.linkname = "/etc/passwd"
                member.size = 0
            archive.addfile(member, io.BytesIO(data))
    with pytest.raises(ValueError):
        verify_archive(kit, {"pool/source": {"size": 5, "sha256": digest(b"input")}})


def test_corrupt_cache_is_detected_before_use(tmp_path: Path) -> None:
    (tmp_path / "package.dsc").write_bytes(b"wrong")
    with pytest.raises(ValueError, match="Cached bytes differ"):
        obtain(tmp_path, "package.dsc", {"size": 5, "sha256": digest(b"right")}, [], False)
