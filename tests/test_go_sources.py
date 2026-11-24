import copy
import io
import json
import shutil
import tarfile
import warnings
import zipfile
from pathlib import Path
from typing import Any

import pytest

from scripts import go_sources as go


@pytest.fixture
def evidence(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    target = tmp_path / "evidence"
    shutil.copytree(go.EVIDENCE, target)
    return go.object_json((target / "source-plan.json").read_bytes()), target


def update(plan: dict[str, Any], directory: Path, name: str, raw: bytes) -> None:
    (directory / name).write_bytes(raw)
    plan["evidence"][name] = go.file_spec(directory / name)


def test_published_plan_has_complete_roles_and_591_inputs() -> None:
    plan = go.check_repository()
    assert len(plan["modules"]) == 591
    assert sum(r["kind"] == "zip" for r in plan["modules"]) == 221
    assert {r for m in plan["modules"] for r in m["roles"]} == {"db", "proxy"}


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "sum", "role", "url", "size"])
def test_module_plan_mutations_fail(evidence: tuple[dict[str, Any], Path], mutation: str) -> None:
    plan, directory = evidence
    row = plan["modules"][0]
    if mutation == "missing":
        plan["modules"].pop()
    elif mutation == "duplicate":
        plan["modules"].append(copy.deepcopy(row))
    elif mutation == "sum":
        row["h1"] = "h1:" + "A" * 43 + "="
    elif mutation == "role":
        row["roles"] = ["db", "proxy"]
    elif mutation == "url":
        row["url"] = "https://example.com/archive.zip"
    else:
        row["size"] = -1
    with pytest.raises(ValueError):
        go.validate_plan(plan, directory)


@pytest.mark.parametrize(
    "mutation", ["identity", "version", "deps", "sum", "notice", "main-source"]
)
def test_rehashed_evidence_cannot_change_binding(
    evidence: tuple[dict[str, Any], Path], mutation: str
) -> None:
    plan, directory = evidence
    if mutation == "identity":
        raw = json.loads((directory / "runtime.json").read_bytes())
        raw["db"]["image_id"] = "sha256:" + "0" * 64
        update(plan, directory, "runtime.json", go.json_bytes(raw))
    elif mutation == "version":
        raw = json.loads((directory / "db-go-env.json").read_bytes())
        raw["GOVERSION"] = "go1.26.9"
        update(plan, directory, "db-go-env.json", go.json_bytes(raw))
    elif mutation == "deps":
        update(plan, directory, "db-build-info.txt", b"/out/gosu: go1.26.10\n")
    elif mutation == "sum":
        update(plan, directory, "db-go.sum", b"")
    elif mutation == "notice":
        update(plan, directory, "go-LICENSE", b"different notice\n")
    else:
        plan["sources"][1]["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        go.validate_plan(plan, directory)


def test_unhashed_evidence_edit_is_rejected(evidence: tuple[dict[str, Any], Path]) -> None:
    plan, directory = evidence
    (directory / "proxy-main.go").write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256"):
        go.validate_plan(plan, directory)


def test_duplicate_json_and_go_sum_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate JSON"):
        go.object_json(b'{"a":1,"a":2}')
    row = b"example.com/m v1.0.0 h1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n"
    with pytest.raises(ValueError, match="Duplicate go.sum"):
        go.sums(row + row)


@pytest.mark.parametrize("path", ["../file", "/file", "a/../b", "C:file", "a\\b", "a\nb", "a//b"])
def test_paths_are_never_normalized_or_extracted(path: str) -> None:
    with pytest.raises(ValueError, match="Unsafe"):
        go.safe_path(path)


def test_module_proxy_case_escaping() -> None:
    assert go.escaped("github.com/Owner/Module") == "github.com/!owner/!module"


@pytest.mark.parametrize("fault", ["prefix", "duplicate", "symlink", "parent", "limit"])
def test_invalid_zip_members_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    path = tmp_path / "module.zip"
    name = "example.com/m@v1.0.0/file.go"
    if fault == "prefix":
        name = "example.com/m@v2.0.0/file.go"
    elif fault == "parent":
        name = "example.com/m@v1.0.0/../file.go"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w") as archive:
            entry = zipfile.ZipInfo(name)
            if fault == "symlink":
                entry.create_system = 3
                entry.external_attr = 0o120777 << 16
            archive.writestr(entry, b"hello")
            if fault == "duplicate":
                archive.writestr(name, b"other")
    if fault == "limit":
        monkeypatch.setattr(go, "LIMIT", 4)
    with pytest.raises(ValueError):
        go.module_hash(path, {"name": "example.com/m", "version": "v1.0.0", "kind": "zip"})


def test_go_mod_checksum_golden(tmp_path: Path) -> None:
    # This exact go.mod and its h1 are recorded by the real gosu builder.
    path = tmp_path / "module.mod"
    path.write_bytes(b"module golang.org/x/sys\n\ngo 1.17\n")
    row = next(
        r
        for r in go.check_repository()["modules"]
        if r["name"] == "golang.org/x/sys" and r["version"] == "v0.1.0" and r["kind"] == "mod"
    )
    assert go.module_hash(path, row) == row["h1"]


@pytest.mark.parametrize("fault", ["missing", "changed", "link", "duplicate", "parent"])
def test_root_tar_observations_are_regular_and_exact(tmp_path: Path, fault: str) -> None:
    path = tmp_path / "root.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("root/VERSION" if fault != "parent" else "root/../VERSION")
        raw = b"other" if fault == "changed" else b"go1.26.10"
        member.size = len(raw)
        if fault == "link":
            member.type, member.linkname, member.size = tarfile.SYMTYPE, "elsewhere", 0
        if fault != "missing":
            archive.addfile(member, io.BytesIO(raw))
        if fault == "duplicate":
            archive.addfile(member, io.BytesIO(raw))
    with pytest.raises(ValueError):
        go.verify_tar(path, "root", {"root/VERSION": b"go1.26.10"})


def test_unobserved_tar_link_is_opaque(tmp_path: Path) -> None:
    path = tmp_path / "root.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("root/.dockerignore")
        member.type, member.linkname = tarfile.SYMTYPE, ".gitignore"
        archive.addfile(member)
    go.verify_tar(path, "root", {})
    assert not (tmp_path / "root").exists()


def test_collection_preserves_failure_and_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "kit"
    with pytest.raises(FileNotFoundError):
        go.collect(output, tmp_path / "missing-inputs", False)
    assert (output / "INCOMPLETE.txt").exists()
    with pytest.raises(FileExistsError):
        go.collect(output, tmp_path, False)


@pytest.mark.parametrize("fault", ["hash", "extra", "file", "coverage"])
def test_manifest_tampering_fails_before_source_processing(tmp_path: Path, fault: str) -> None:
    raw = b"{}"
    (tmp_path / "source-plan.json").write_bytes(raw)
    manifest: dict[str, Any] = {
        "schema": "marketob-go-kit/v1",
        "files": {"source-plan.json": go.file_spec(tmp_path / "source-plan.json")},
    }
    if fault == "coverage":
        raw = go.json_bytes({"evidence": {}, "modules": [], "sources": []})
        (tmp_path / "source-plan.json").write_bytes(raw)
        manifest["files"]["source-plan.json"] = go.file_spec(tmp_path / "source-plan.json")
    (tmp_path / "manifest.json").write_bytes(go.json_bytes(manifest))
    expected = go.file_spec(tmp_path / "manifest.json")["sha256"]
    if fault == "hash":
        expected = "0" * 64
    elif fault == "extra":
        (tmp_path / "unexpected").write_bytes(b"extra")
    elif fault == "file":
        (tmp_path / "source-plan.json").write_bytes(b"changed")
    with pytest.raises(ValueError):
        go.verify(tmp_path, expected)
