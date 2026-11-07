"""The handover verifier must work offline and reject misleading archive layouts."""

import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

from scripts.delivery_bundle import ROOT, check_recipe, file_hash, pack, verify


def identity() -> dict[str, Any]:
    return {
        "release_commit": "a" * 40,
        "tooling_commit": "b" * 40,
        "coverage_state": "partial",
        "open_items": ["review"],
        "images": {role: "sha256:" + "c" * 64 for role in ("api", "bot", "db", "proxy")},
    }


def kit(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    source = tmp_path / "source"
    source.write_bytes(b"reviewed source\n")
    path = tmp_path / "kit.tar"
    result = pack(path, {"sources/input.tar": source}, identity())
    return path, result


def altered(tmp_path: Path, failure: str) -> Path:
    original, result = kit(tmp_path)
    manifest = result["manifest"]
    if failure == "unsafe_path":
        manifest["files"][0]["name"] = "../escape"
    elif failure == "duplicate_row":
        manifest["files"].append(manifest["files"][0])
    elif failure == "false_complete":
        manifest["coverage_state"] = "complete"
    elif failure == "wrong_images":
        manifest["images"].pop("api")
    raw = json.dumps(manifest).encode()
    if failure == "duplicate_json":
        raw = raw[:-1] + b', "files": []}'
    path = tmp_path / "altered.tar"
    with tarfile.open(path, "w") as archive:
        header = tarfile.TarInfo("manifest.json")
        header.size = len(raw)
        archive.addfile(header, io.BytesIO(raw))
        with tarfile.open(original) as before:
            member = before.getmember("sources/input.tar")
            source = before.extractfile(member)
            assert source is not None
            data = source.read()
            if failure == "missing":
                return path
            if failure == "corrupt":
                data = b"x" + data[1:]
            if failure == "link":
                member.type, member.linkname, member.size = tarfile.SYMTYPE, "/etc/passwd", 0
            if failure == "unexpected":
                member.name = "extra"
            archive.addfile(member, io.BytesIO(data))
            if failure == "duplicate":
                archive.addfile(member, io.BytesIO(data))
    return path


def test_round_trip_and_no_overwrite(tmp_path: Path) -> None:
    path, result = kit(tmp_path)
    manifest = verify(path, result["sha256"])
    assert manifest["coverage_state"] == "partial"
    assert manifest["open_items"] == ["review"]
    with pytest.raises(FileExistsError):
        pack(path, {}, identity())


def test_external_digest_binds_whole_archive(tmp_path: Path) -> None:
    path, result = kit(tmp_path)
    with path.open("ab") as stream:
        stream.write(b"unreviewed trailing content")
    with pytest.raises(ValueError, match="Whole archive"):
        verify(path, result["sha256"])


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "corrupt",
        "link",
        "unexpected",
        "duplicate",
        "unsafe_path",
        "duplicate_row",
        "false_complete",
        "wrong_images",
        "duplicate_json",
    ],
)
def test_invalid_layout_even_with_recomputed_outer_hash(tmp_path: Path, failure: str) -> None:
    path = altered(tmp_path, failure)
    with pytest.raises(ValueError):
        verify(path, file_hash(path))


def test_verifier_runs_standalone_without_checkout(tmp_path: Path) -> None:
    path, result = kit(tmp_path)
    standalone = tmp_path / "verify_bundle.py"
    shutil.copyfile(ROOT / "scripts/delivery_bundle.py", standalone)
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            str(standalone),
            "--verify",
            str(path),
            "--sha256",
            result["sha256"],
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    assert json.loads(process.stdout)["integrity"] == "verified"


def test_release_recipe_binds_current_evidence() -> None:
    recipe = check_recipe()
    assert recipe["release_commit"] == "68958f1bba16df49159d13fd9e99b47f7d924956"
    assert len(recipe["sources"]) == 4
