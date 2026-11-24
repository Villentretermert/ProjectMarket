"""Source delivery must cover the installed inventory and reject altered evidence."""

import copy
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any, Literal

import pytest

from scripts.python_sources import (
    ROOT,
    collect,
    digest,
    file_digest,
    plan,
    repository_context,
    validate_sdist,
    verify,
)


def tar_bytes(
    files: dict[str, bytes], mode: Literal["w:", "w:gz"] = "w:", fault: str = ""
) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode=mode) as archive:
        for name, raw in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            if fault == "metadata-link" and name.endswith("PKG-INFO"):
                member.type, member.linkname, member.size = tarfile.SYMTYPE, "/secret", 0
            archive.addfile(member, io.BytesIO(raw))
            if fault == "duplicate":
                archive.addfile(member, io.BytesIO(raw))
        if fault == "source-link":
            member = tarfile.TarInfo("sample-1.0/CHANGELOG")
            member.type, member.linkname = tarfile.SYMTYPE, "docs/changes"
            archive.addfile(member)
    return buffer.getvalue()


def fixture() -> tuple[dict[str, Any], dict[str, bytes]]:
    sdist = tar_bytes({"sample-1.0/PKG-INFO": b"Name: Sample\nVersion: 1.0\n\n"}, "w:gz")
    lock = (
        '[[package]]\nname = "sample"\nversion = "1.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        'sdist = { url = "https://files.pythonhosted.org/packages/ab/sample-1.0.tar.gz", '
        f'hash = "sha256:{digest(sdist)}", size = {len(sdist)} }}\n'
    ).encode()
    inventory = {
        "images": [
            {
                "role": role,
                "id": "sha256:" + str(index) * 64,
                "os": "linux",
                "architecture": "amd64",
                "components": (
                    [{"ecosystem": "pypi", "name": "Sample", "version": "1.0"}]
                    if role in {"api", "bot"}
                    else []
                ),
            }
            for index, role in enumerate(("api", "bot", "db", "proxy"))
        ]
    }
    raw = json.dumps(inventory).encode()
    manifest = plan(raw, lock, "a" * 40)
    return manifest, {
        "inventory.json": raw,
        "uv.lock": lock,
        "manifest.json": json.dumps(manifest).encode(),
        "verify.py": b"# Placeholder; actual standalone verifier is tested separately.\n",
        manifest["inputs"][0]["path"]: sdist,
    }


def test_published_plan_covers_all_installed_runtime_packages() -> None:
    manifest, context = repository_context()
    assert len(manifest["inputs"]) == 30
    assert {r for p in manifest["inputs"] for r in p["images"]} == {"api", "bot"}
    assert sum("api" in p["images"] for p in manifest["inputs"]) == 29
    assert sum("bot" in p["images"] for p in manifest["inputs"]) == 6
    assert digest(context["uv.lock"]) == manifest["lock_sha256"]


def test_standalone_verification_needs_no_repo_network_or_packages(tmp_path: Path) -> None:
    manifest, files = fixture()
    archive = tmp_path / "sources.tar"
    archive.write_bytes(tar_bytes(files))
    script = tmp_path / "verify.py"
    script.write_bytes((ROOT / "scripts/python_sources.py").read_bytes())
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(script),
            "--verify",
            str(archive),
            "--sha256",
            file_digest(archive),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    receipt = json.loads(result.stdout)
    assert receipt["images"] == manifest["images"]
    assert receipt["verified_sdists"][0]["name"] == "sample"


@pytest.mark.parametrize(
    "fault",
    [
        "omitted",
        "version",
        "image",
        "url",
        "hash",
        "scope",
        "lock",
        "inventory",
        "extra",
        "missing",
        "bytes",
        "duplicate",
        "path",
        "external-hash",
    ],
)
def test_archive_rejects_incomplete_or_tampered_evidence(tmp_path: Path, fault: str) -> None:
    manifest, files = fixture()
    spec = manifest["inputs"][0]
    if fault == "omitted":
        manifest["inputs"] = []
    elif fault in {"version", "url", "hash"}:
        spec[{"hash": "sha256"}.get(fault, fault)] = "changed"
    elif fault == "image":
        spec["images"]["bot"] = "sha256:" + "f" * 64
    elif fault == "scope":
        manifest["coverage_state"] = "complete"
    elif fault == "lock":
        files["uv.lock"] = files["uv.lock"].replace(b'version = "1.0"', b'version = "9.0"')
    elif fault == "inventory":
        inventory = json.loads(files["inventory.json"])
        inventory["images"][0]["components"][0]["name"] = "absent"
        files["inventory.json"] = json.dumps(inventory).encode()
    elif fault == "extra":
        files[".env"] = b"unexpected private file"
    elif fault == "missing":
        del files[spec["path"]]
    elif fault == "bytes":
        files[spec["path"]] += b"changed"
    elif fault == "path":
        files["../outside"] = b"invalid"
    files["manifest.json"] = json.dumps(manifest).encode()
    archive = tmp_path / "sources.tar"
    archive.write_bytes(tar_bytes(files, fault="duplicate" if fault == "duplicate" else ""))
    with pytest.raises(ValueError):
        verify(archive, "0" * 64 if fault == "external-hash" else file_digest(archive))


@pytest.mark.parametrize(
    "fault", ["identity", "missing", "duplicate-header", "metadata-link", "duplicate", "traversal"]
)
def test_sdist_checks_metadata_and_never_follows_links(fault: str) -> None:
    headers = b"Name: Sample\nVersion: 1.0\n\n"
    if fault == "identity":
        headers = headers.replace(b"1.0", b"9.0")
    elif fault == "duplicate-header":
        headers = b"Name: Sample\nName: Other\nVersion: 1.0\n\n"
    name = "sample-1.0/PKG-INFO" if fault != "missing" else "sample-1.0/README"
    if fault == "traversal":
        name = "../sample-1.0/PKG-INFO"
    raw = tar_bytes({name: headers}, "w:gz", fault)
    spec = {"name": "sample", "version": "1.0", "size": len(raw), "sha256": digest(raw)}
    with pytest.raises(ValueError):
        validate_sdist(raw, spec)


def test_upstream_nonmetadata_link_is_preserved_as_opaque_data() -> None:
    raw = tar_bytes(
        {"sample-1.0/PKG-INFO": b"Name: Sample\nVersion: 1.0\n\n"}, "w:gz", "source-link"
    )
    spec = {"name": "sample", "version": "1.0", "size": len(raw), "sha256": digest(raw)}
    assert validate_sdist(raw, spec)["name"] == "sample"


@pytest.mark.parametrize(
    "fault",
    ["duplicate-package", "duplicate-role", "missing-sdist", "duplicate-lock", "unsafe-url"],
)
def test_plan_fails_on_ambiguous_or_missing_mapping(fault: str) -> None:
    _, files = fixture()
    inventory = json.loads(files["inventory.json"])
    lock = files["uv.lock"]
    if fault == "duplicate-package":
        inventory["images"][0]["components"] *= 2
    elif fault == "duplicate-role":
        inventory["images"].append(copy.deepcopy(inventory["images"][0]))
    elif fault == "missing-sdist":
        lock = lock.split(b"sdist =")[0]
    elif fault == "duplicate-lock":
        lock *= 2
    elif fault == "unsafe-url":
        lock = lock.replace(b"https://files.pythonhosted.org", b"http://localhost")
    with pytest.raises(ValueError):
        plan(json.dumps(inventory).encode(), lock, "a" * 40)


def test_offline_collect_refuses_corrupt_cache_and_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, files = fixture()
    context = {k: v for k, v in files.items() if k in {"inventory.json", "uv.lock"}}
    monkeypatch.setattr("scripts.python_sources.repository_context", lambda: (manifest, context))
    monkeypatch.setattr("scripts.python_sources.ROOT", tmp_path)
    monkeypatch.setattr("scripts.python_sources.MANIFEST", "manifest.json")
    (tmp_path / "manifest.json").write_bytes(files["manifest.json"])
    cache = tmp_path / "cache"
    cache.mkdir()
    spec = manifest["inputs"][0]
    cached = cache / spec["sha256"]
    raw = files[spec["path"]]
    cached.write_bytes(b"x" + raw[1:])
    output = tmp_path / "bad"
    with pytest.raises(ValueError, match="SHA-256"):
        collect(output, cache, False)
    assert (output / "INCOMPLETE.txt").is_file()
    cached.write_bytes(raw)
    receipt = collect(tmp_path / "good", cache, False)
    assert receipt["verified_sdists"][0]["name"] == "sample"
    with pytest.raises(FileExistsError):
        collect(tmp_path / "good", cache, False)
