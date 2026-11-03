"""Reject broken producer evidence without executing downloaded code."""

import copy
import io
import json
import shutil
import struct
import tarfile
from pathlib import Path
from typing import Any

import pytest

from scripts.collect_notices import ROOT, digest
from scripts.native_notices import (
    distribution_notices,
    elf_evidence,
    evidence_files,
    proof,
    run,
    summarize_sbom,
)


def elf_fixture(defined: bool = True) -> bytes:
    strings = b"\0.shstrtab\0.comment\0.dynstr\0.dynsym\0"
    comment = b"rustc version 1.0.0 (abcdefghi 2000-01-01)\0"
    dynamic = b"\0cffistatic_ffi_call\0"
    symbol = struct.pack("<IBBHQQ", 1, 18, 0, 2 if defined else 0, 0, 12)
    sections = [(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)]
    body = bytearray(64)
    for name, kind, data, link, size in [
        (".shstrtab", 3, strings, 0, 0),
        (".comment", 1, comment, 0, 0),
        (".dynstr", 3, dynamic, 0, 0),
        (".dynsym", 11, symbol, 3, 24),
    ]:
        sections.append(
            (strings.index(name.encode()), kind, 0, 0, len(body), len(data), link, 0, 1, size)
        )
        body.extend(data)
    offset = len(body)
    for section in sections:
        body.extend(struct.pack("<IIQQQQIIQQ", *section))
    body[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<Q", body, 40, offset)
    struct.pack_into("<HHH", body, 58, 64, len(sections), 1)
    return bytes(body)


def test_defined_static_function_required() -> None:
    assert elf_evidence(elf_fixture())["defined_markers"] == ["cffistatic_ffi_call"]
    assert elf_evidence(elf_fixture(False))["defined_markers"] == []


@pytest.mark.parametrize("fault", ["class", "truncate", "section", "strings", "symbols"])
def test_invalid_elf_rejected(fault: str) -> None:
    raw = bytearray(elf_fixture())
    offset = struct.unpack_from("<Q", raw, 40)[0]
    if fault == "class":
        raw[4] = 1
    elif fault == "truncate":
        raw = raw[:60]
    elif fault == "section":
        struct.pack_into("<Q", raw, 40, len(raw) + 10)
    elif fault == "strings":
        struct.pack_into("<I", raw, offset + 2 * 64, 9999)
    else:
        struct.pack_into("<Q", raw, offset + 4 * 64 + 56, 23)
    with pytest.raises(ValueError):
        elf_evidence(bytes(raw))


@pytest.fixture
def sbom_case() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    root = {"name": "demo", "version": "1", "bom-ref": "path+file:///public/producer#demo@1"}
    crate = {
        "name": "leaf",
        "version": "2",
        "bom-ref": "registry+https://github.com/rust-lang/crates.io-index#leaf@2",
        "hashes": [{"alg": "SHA-256", "content": "a" * 64}],
    }
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "metadata": {
            "component": root,
            "properties": [{"name": "cdx:rustc:sbom:target:all_targets", "value": "true"}],
        },
        "components": [crate],
        "dependencies": [
            {"ref": root["bom-ref"], "dependsOn": [crate["bom-ref"]]},
            {"ref": crate["bom-ref"]},
        ],
    }
    parent = {
        "name": "demo",
        "version": "1",
        "workspace_entries": [{"name": "demo", "version": "1", "member": "Cargo.toml"}],
    }
    inputs = [
        {"kind": "crate", "name": "leaf", "version": "2", "sha256": "a" * 64, "parents": ["demo"]}
    ]
    return bom, parent, inputs


def test_sbom_normalizes_paths_and_missing_leaf_edges(sbom_case: tuple[Any, ...]) -> None:
    result = summarize_sbom(*sbom_case)
    assert result["dependencies"] == {"demo@1": ["leaf@2"], "leaf@2": []}
    assert "public/producer" not in json.dumps(result)
    assert "all targets" in result["scope"]


@pytest.mark.parametrize(
    "fault",
    [
        "root",
        "scope",
        "hash",
        "duplicate",
        "dangling",
        "missing",
        "unreachable",
        "duplicate_edge",
        "unbound",
    ],
)
def test_broken_sbom_rejected(sbom_case: tuple[Any, ...], fault: str) -> None:
    bom, parent, inputs = sbom_case
    if fault == "root":
        bom["metadata"]["component"]["version"] = "999"
    elif fault == "scope":
        bom["metadata"]["properties"] = []
    elif fault == "hash":
        bom["components"][0]["hashes"][0]["content"] = "b" * 64
    elif fault == "duplicate":
        bom["components"].append(copy.deepcopy(bom["components"][0]))
    elif fault == "dangling":
        bom["dependencies"][0]["dependsOn"].append("missing")
    elif fault == "missing":
        bom["dependencies"].pop()
    elif fault == "unreachable":
        bom["dependencies"][0]["dependsOn"] = []
    elif fault == "duplicate_edge":
        bom["dependencies"][0]["dependsOn"] *= 2
    else:
        inputs[0]["parents"] = []
    with pytest.raises(ValueError):
        summarize_sbom(bom, parent, inputs)


@pytest.fixture
def saved() -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
    directory = ROOT / "third_party/native-68958f1"
    manifest = json.loads((directory / "sources.json").read_text(encoding="utf-8"))
    embedded = json.loads(
        (ROOT / "third_party/embedded-68958f1/sources.json").read_text(encoding="utf-8")
    )
    return manifest, embedded, evidence_files(directory, manifest)


@pytest.mark.parametrize("fault", ["compiler", "coverage", "ffi", "file", "channel", "license"])
def test_invalid_native_association(saved: tuple[Any, ...], fault: str) -> None:
    manifest, embedded, files = saved
    if fault == "compiler":
        manifest["toolchains"][0]["commit"] = "f" * 40
    elif fault == "coverage":
        manifest["wheels"].pop()
    elif fault == "ffi":
        manifest["libffi"]["version"] = "0.0.0"
    elif fault == "file":
        manifest["wheels"][0]["native"][0]["file"]["sha256"] = "f" * 64
    elif fault == "channel":
        manifest["toolchains"][0]["distribution"]["sha256"] = "f" * 64
    else:
        manifest["libffi"]["license"]["notices"][0]["sha256"] = "f" * 64
    with pytest.raises(ValueError):
        proof(manifest, embedded, files)


def test_committed_evidence_and_prior_gaps() -> None:
    run(
        ROOT / "third_party/native-68958f1",
        ROOT / "third_party/68958f1-embedded",
        ROOT / "third_party/embedded-68958f1/sources.json",
        ROOT / "third_party/68958f1-native",
    )
    report = json.loads(
        (ROOT / "third_party/68958f1-native/inventory.json").read_text(encoding="utf-8")
    )
    assert len(report["embedded_source_evidence"]["notice_gaps"]) == 10
    assert len(report["embedded_source_evidence"]["workspace_gaps"]) == 5
    assert len(report["native_build_evidence"]["sboms"]) == 3


def test_altered_evidence_archive_rejected(saved: tuple[Any, ...], tmp_path: Path) -> None:
    manifest, _, _ = saved
    (tmp_path / "evidence.tar.gz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="archive changed"):
        evidence_files(tmp_path, manifest)


def test_prior_gaps_cannot_be_removed(tmp_path: Path) -> None:
    original = ROOT / "third_party/68958f1-native"
    shutil.copyfile(original / "texts.tar.gz", tmp_path / "texts.tar.gz")
    report = json.loads((original / "inventory.json").read_text(encoding="utf-8"))
    report["embedded_source_evidence"]["notice_gaps"].pop()
    (tmp_path / "inventory.json").write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="Prior inventory or gaps changed"):
        run(
            ROOT / "third_party/native-68958f1",
            ROOT / "third_party/68958f1-embedded",
            ROOT / "third_party/embedded-68958f1/sources.json",
            tmp_path,
        )


@pytest.mark.parametrize("fault", [None, "duplicate", "link", "hash", "missing"])
def test_distribution_members(fault: str | None) -> None:
    stream = io.BytesIO()
    data = b"Upstream notice"
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for _ in range(2 if fault == "duplicate" else 1):
            member = tarfile.TarInfo("LICENSE")
            member.size = len(data)
            if fault == "link":
                member.type, member.linkname = tarfile.SYMTYPE, "elsewhere"
            archive.addfile(member, io.BytesIO(data))
    selections = [
        {
            "member": "MISSING" if fault == "missing" else "LICENSE",
            "sha256": "f" * 64 if fault == "hash" else digest(data),
        }
    ]
    if fault:
        with pytest.raises(ValueError):
            distribution_notices(stream.getvalue(), selections)
    else:
        assert distribution_notices(stream.getvalue(), selections) == {digest(data): data}
