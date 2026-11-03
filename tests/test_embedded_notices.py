"""Evidence integrity checks; no network, container or downloaded code execution."""

import copy
import io
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest

from scripts.collect_notices import Collector, digest, write_bundle
from scripts.embedded_notices import (
    collect,
    locked_crates,
    tar_member,
    validate_manifest,
    verify_supplement,
    verify_wheel,
)


def archive_bytes(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, raw in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
    return stream.getvalue()


def wheel_bytes(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)
    return stream.getvalue()


@pytest.fixture
def case(tmp_path: Path) -> dict[str, Any]:
    base, cache, output = (tmp_path / n for n in ("base", "cache", "output"))
    for path in (base, cache, output):
        path.mkdir()
    collector = Collector(None)
    report = {
        "images": [
            {
                "role": "api",
                "id": "sha256:fixture",
                "components": [
                    {
                        "ecosystem": "pypi",
                        "name": "demo",
                        "version": "1.0",
                        "notices": [collector.record("LICENSE", b"parent notice")],
                    }
                ],
            }
        ],
        "gaps": [{"reason": "prior gap must stay"}],
    }
    write_bundle(base, report, collector.texts)
    crate = archive_bytes(
        {
            "leaf-1.0.0/Cargo.toml": b'[package]\nname="leaf"\nversion="1.0.0"\nlicense="MIT"\n',
            "leaf-1.0.0/LICENSE": b"leaf notice",
        }
    )
    lock = (
        'version=3\n[[package]]\nname="leaf"\nversion="1.0.0"\n'
        'source="registry+https://github.com/rust-lang/crates.io-index"\n'
        f'checksum="{digest(crate)}"\n'
    ).encode()
    (tmp_path / "Cargo.lock").write_bytes(lock)
    sdist = archive_bytes({"demo-1.0/Cargo.lock": lock})
    wheel = wheel_bytes({"demo/native.so": b"native"})
    inputs: list[dict[str, Any]] = [
        {
            "kind": "sdist",
            "path": "demo.tar.gz",
            "name": "demo",
            "version": "1.0",
            "url": "https://example.test/demo.tar.gz",
            "sha256": digest(sdist),
            "notices": [],
        },
        {
            "kind": "wheel",
            "path": "demo.whl",
            "name": "demo",
            "version": "1.0",
            "url": "https://example.test/demo.whl",
            "sha256": digest(wheel),
            "notices": [],
        },
        {
            "kind": "crate",
            "path": "leaf.crate",
            "name": "leaf",
            "version": "1.0.0",
            "url": "https://example.test/leaf.crate",
            "sha256": digest(crate),
            "parents": ["demo"],
            "declared_license": "MIT",
            "notices": [
                {
                    "member": "leaf-1.0.0/LICENSE",
                    "sha256": digest(b"leaf notice"),
                    "kind": "upstream_notice_file",
                }
            ],
        },
    ]
    for spec, raw in zip(inputs, [sdist, wheel, crate], strict=True):
        (cache / spec["path"]).write_bytes(raw)
    manifest = {
        "base_inventory_sha256": digest((base / "inventory.json").read_bytes()),
        "parents": [
            {
                "name": "demo",
                "version": "1.0",
                "images": {"api": "sha256:fixture"},
                "sdist": "demo.tar.gz",
                "wheel": "demo.whl",
                "installed_native_files": [
                    {"path": "demo/native.so", "sha256": digest(b"native"), "bytes": 6}
                ],
                "cargo_lock": {
                    "file": "Cargo.lock",
                    "member": "demo-1.0/Cargo.lock",
                    "sha256": digest(lock),
                },
            }
        ],
        "inputs": inputs,
        "open_items": ["Exact linked graph not established"],
    }
    uv = tmp_path / "uv.lock"
    uv.write_text(
        '[[package]]\nname="demo"\nversion="1.0"\n'
        f'sdist={{url="{inputs[0]["url"]}",hash="sha256:{digest(sdist)}"}}\n'
        f'wheels=[{{url="{inputs[1]["url"]}",hash="sha256:{digest(wheel)}"}}]\n'
    )
    return dict(
        base=base, cache=cache, output=output, manifest=manifest, evidence_dir=tmp_path, uv_lock=uv
    )


def test_collection_retains_inventory_and_binds_source_bytes(case: dict[str, Any]) -> None:
    source_archive = case["evidence_dir"] / "sources.tar.gz"
    collect(**case, source_archive=source_archive)
    verify_supplement(**{k: v for k, v in case.items() if k != "cache"})
    report = json.loads((case["output"] / "inventory.json").read_text())
    assert report["gaps"] == [{"reason": "prior gap must stay"}]
    assert report["unique_notice_texts"] == 2
    with tarfile.open(source_archive) as archive:
        assert set(archive.getnames()) == {"demo.tar.gz", "leaf.crate"}
    report["gaps"] = []
    (case["output"] / "inventory.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="prior gaps"):
        verify_supplement(**{k: v for k, v in case.items() if k != "cache"})


@pytest.mark.parametrize("mutation", ["omit_crate", "checksum", "parent", "image", "lock_bytes"])
def test_manifest_rejects_broken_provenance(case: dict[str, Any], mutation: str) -> None:
    manifest = copy.deepcopy(case["manifest"])
    if mutation == "omit_crate":
        manifest["inputs"].pop()
    elif mutation == "checksum":
        manifest["inputs"][-1]["sha256"] = "0" * 64
    elif mutation == "parent":
        manifest["inputs"][-1]["parents"] = []
    elif mutation == "image":
        manifest["parents"][0]["images"]["api"] = "sha256:other"
    else:
        (case["evidence_dir"] / "Cargo.lock").write_bytes(b"tampered")
    with pytest.raises(ValueError):
        validate_manifest(manifest, case["evidence_dir"], case["base"], case["uv_lock"])


@pytest.mark.parametrize(
    "native",
    [
        {"demo/native.so": b"changed"},
        {"demo/native.so": b"native", "extra.so": b"unrecorded"},
    ],
)
def test_wheel_requires_exact_installed_native_set(native: dict[str, bytes]) -> None:
    files = [{"path": "demo/native.so", "sha256": digest(b"native"), "bytes": 6}]
    with pytest.raises(ValueError, match="native files"):
        verify_wheel(wheel_bytes(native), files)


def test_wheel_rejects_link_as_native_file() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        info = zipfile.ZipInfo("demo/native.so")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, b"native")
    with pytest.raises(ValueError, match="linked"):
        verify_wheel(
            stream.getvalue(), [{"path": "demo/native.so", "sha256": digest(b"native"), "bytes": 6}]
        )


@pytest.mark.parametrize("link", [True, False])
def test_tar_evidence_rejects_links_and_duplicates(link: bool) -> None:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for _ in range(1 if link else 2):
            member = tarfile.TarInfo("Cargo.lock")
            if link:
                member.type, member.linkname = tarfile.SYMTYPE, "/outside"
                archive.addfile(member)
            else:
                member.size = 4
                archive.addfile(member, io.BytesIO(b"data"))
    with pytest.raises(ValueError, match="duplicate, linked"):
        tar_member(stream.getvalue(), "Cargo.lock")


def test_non_registry_lock_requires_review() -> None:
    raw = b'[[package]]\nname="leaf"\nversion="1.0.0"\nsource="git+https://example.test/a#1"\n'
    with pytest.raises(ValueError, match="Non-registry"):
        locked_crates({"demo": raw})


def test_no_notice_is_reported_as_gap(case: dict[str, Any]) -> None:
    case["manifest"]["inputs"][-1]["notices"] = []
    collect(**case)
    report = json.loads((case["output"] / "inventory.json").read_text())
    gaps = report["embedded_source_evidence"]["notice_gaps"]
    assert [(g["name"], g["reason"]) for g in gaps] == [("leaf", "notice_not_found_in_crate")]


def test_collection_rejects_fabricated_upstream_repository(case: dict[str, Any]) -> None:
    case["manifest"]["inputs"][-1]["repository"] = "https://example.test/unrelated"
    with pytest.raises(ValueError, match="repository differs"):
        collect(**case)


def test_workspace_entries_cannot_be_silently_dropped(case: dict[str, Any]) -> None:
    lock_path = case["evidence_dir"] / "Cargo.lock"
    raw = lock_path.read_bytes() + b'[[package]]\nname="local-crate"\nversion="1.0.0"\n'
    lock_path.write_bytes(raw)
    parent = case["manifest"]["parents"][0]
    parent["cargo_lock"]["sha256"] = digest(raw)
    with pytest.raises(ValueError, match="Workspace entry coverage"):
        validate_manifest(case["manifest"], case["evidence_dir"], case["base"], case["uv_lock"])
    parent["workspace_entries"] = [{"name": "local-crate", "version": "1.0.0", "member": None}]
    validate_manifest(case["manifest"], case["evidence_dir"], case["base"], case["uv_lock"])
