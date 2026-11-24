"""The CPython supplement must stay bound to both installed images and source bytes."""

import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

from scripts.cpython_sources import (
    EVIDENCE,
    ROOT,
    check_repository,
    collect,
    digest,
    file_digest,
    file_spec,
    json_bytes,
    verify,
)


def source_tar(license_raw: bytes, header: bytes, fault: str = "") -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:xz") as archive:
        for name, raw in {"LICENSE": license_raw, "Include/patchlevel.h": header}.items():
            member = tarfile.TarInfo("Python-3.14.9/" + name)
            member.size = len(raw)
            if fault == "link" and name == "LICENSE":
                member.type, member.linkname, member.size = tarfile.SYMTYPE, "/private", 0
            if fault == "path":
                member.name = "../" + member.name
            archive.addfile(member, io.BytesIO(raw))
            if fault == "duplicate":
                archive.addfile(member, io.BytesIO(raw))
    return stream.getvalue()


def seal(directory: Path) -> str:
    manifest = {
        "schema": "marketob-cpython-kit/v1",
        "files": {
            p.name: file_spec(p) for p in sorted(directory.iterdir()) if p.name != "manifest.json"
        },
    }
    raw = json_bytes(manifest)
    (directory / "manifest.json").write_bytes(raw)
    return digest(raw)


def set_source(directory: Path, raw: bytes) -> None:
    plan = json.loads((directory / "source-plan.json").read_bytes())
    runtime = json.loads((directory / "runtime.json").read_bytes())
    (directory / plan["source"]["filename"]).write_bytes(raw)
    plan["source"].update(size=len(raw), sha256=digest(raw), published_sha256=digest(raw))
    for row in runtime.values():
        row["source_env"]["PYTHON_SHA256"] = digest(raw)
    (directory / "runtime.json").write_bytes(json_bytes(runtime))
    plan["runtime_sha256"] = file_digest(directory / "runtime.json")
    (directory / "source-plan.json").write_bytes(json_bytes(plan))


def fixture(directory: Path) -> dict[str, Any]:
    directory.mkdir()
    for path in EVIDENCE.iterdir():
        (directory / path.name).write_bytes(path.read_bytes())
    (directory / "verify.py").write_bytes((ROOT / "scripts/cpython_sources.py").read_bytes())
    raw = source_tar(
        (directory / "LICENSE.txt").read_bytes(), (directory / "patchlevel.h").read_bytes()
    )
    set_source(directory, raw)
    seal(directory)
    result = json.loads((directory / "source-plan.json").read_bytes())
    assert isinstance(result, dict)
    return result


def test_published_plan_is_bound_to_installed_release() -> None:
    plan = check_repository()
    assert plan["source"]["version"] == "3.14.9"
    assert (
        plan["source"]["sha256"]
        == "e02d9ac21cebda6e46435369744a92c65cc7cd8669697694122cf97ffacd1e53"
    )
    assert set(plan["images"]) == {"api", "bot"}


def test_verifier_runs_standalone_without_repo_imports(tmp_path: Path) -> None:
    directory = tmp_path / "kit"
    fixture(directory)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(directory / "verify.py"),
            "--verify",
            str(directory),
            "--sha256",
            file_digest(directory / "manifest.json"),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(result.stdout)
    assert data["members"] == 2
    assert set(data["matched_source_files"]) == {"license", "patchlevel"}


@pytest.mark.parametrize(
    "fault",
    [
        "image",
        "scope",
        "role",
        "source-env",
        "runtime-version",
        "flags-drift",
        "license-notice",
        "wrong-url",
        "changed-text",
        "missing",
        "extra",
        "source-bytes",
        "external-hash",
    ],
)
def test_kit_rejects_invalid_source_or_runtime_binding(tmp_path: Path, fault: str) -> None:
    directory = tmp_path / "kit"
    plan = fixture(directory)
    runtime = json.loads((directory / "runtime.json").read_bytes())
    inventory = json.loads((directory / "inventory.json").read_bytes())
    if fault == "image":
        plan["images"]["bot"] = "sha256:" + "f" * 64
    elif fault == "scope":
        plan["coverage_state"] = "complete"
    elif fault == "role":
        del runtime["bot"]
    elif fault == "source-env":
        runtime["bot"]["source_env"]["PYTHON_SHA256"] = "f" * 64
    elif fault == "runtime-version":
        runtime["bot"]["version"] = "3.14.99"
    elif fault == "flags-drift":
        runtime["bot"]["config_args"] += " --different"
    elif fault == "license-notice":
        row = next(r for r in inventory["images"] if r["role"] == "api")
        next(p for p in row["components"] if p["ecosystem"] == "runtime")["notices"][0][
            "sha256"
        ] = "f" * 64
    elif fault == "wrong-url":
        plan["source"]["url"] = "https://example.com/untrusted.tar.xz"
    elif fault == "changed-text":
        (directory / "Makefile").write_bytes(b"changed")
    elif fault == "missing":
        (directory / "README.md").unlink()
    elif fault == "extra":
        (directory / ".env").write_bytes(b"unexpected")
    elif fault == "source-bytes":
        (directory / plan["source"]["filename"]).write_bytes(b"changed")
    (directory / "runtime.json").write_bytes(json_bytes(runtime))
    (directory / "inventory.json").write_bytes(json_bytes(inventory))
    plan["runtime_sha256"] = file_digest(directory / "runtime.json")
    plan["inventory_sha256"] = file_digest(directory / "inventory.json")
    (directory / "source-plan.json").write_bytes(json_bytes(plan))
    external = seal(directory)
    with pytest.raises(ValueError):
        verify(directory, "0" * 64 if fault == "external-hash" else external)


@pytest.mark.parametrize("fault", ["license", "patchlevel-version", "link", "duplicate", "path"])
def test_source_archive_is_checked_beyond_compressed_digest(tmp_path: Path, fault: str) -> None:
    directory = tmp_path / "kit"
    plan = fixture(directory)
    license_raw, header = (
        (directory / "LICENSE.txt").read_bytes(),
        (directory / "patchlevel.h").read_bytes(),
    )
    if fault == "license":
        license_raw += b"changed"
    if fault == "patchlevel-version":
        header = header.replace(b'"3.14.9"', b'"3.14.99"')
        (directory / "patchlevel.h").write_bytes(header)
        runtime = json.loads((directory / "runtime.json").read_bytes())
        for row in runtime.values():
            row["files"]["patchlevel"].update(size=len(header), sha256=digest(header))
        (directory / "runtime.json").write_bytes(json_bytes(runtime))
    set_source(directory, source_tar(license_raw, header, fault))
    assert (directory / plan["source"]["filename"]).exists()
    with pytest.raises(ValueError):
        verify(directory, seal(directory))


def test_duplicate_manifest_keys_are_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "kit"
    fixture(directory)
    path = directory / "manifest.json"
    raw = path.read_bytes().replace(b'"schema":', b'"schema":"duplicate","schema":', 1)
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="Duplicate JSON"):
        verify(directory, digest(raw))


def test_bad_collection_is_marked_and_good_output_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "evidence"
    plan = fixture(evidence)
    monkeypatch.setattr("scripts.cpython_sources.EVIDENCE", evidence)
    monkeypatch.setattr("scripts.cpython_sources.check_repository", lambda: plan)
    bad = tmp_path / "invalid-source"
    bad.write_bytes(b"invalid")
    with pytest.raises(ValueError, match="SHA-256"):
        collect(tmp_path / "bad", bad, False)
    assert (tmp_path / "bad/INCOMPLETE.txt").is_file()
    result = collect(tmp_path / "good", evidence / plan["source"]["filename"], False)
    assert result["members"] == 2
    with pytest.raises(FileExistsError):
        collect(tmp_path / "good", evidence / plan["source"]["filename"], False)
