"""Source notices must stay bound to the shipped version and exact source bytes."""

import copy
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from scripts.alpine_notices import (
    read_source,
    safe_path,
    selected_notice,
    verify_recipe,
    verify_supplement,
)
from scripts.collect_notices import ROOT, digest


@pytest.mark.parametrize("name", ["../secret", "/etc/LICENSE", "C:/private/LICENSE", "a\\LICENSE"])
def test_source_paths_stay_in_cache(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="Unsafe source path"):
        safe_path(tmp_path, name)


def test_read_source_refuses_corrupt_cache(tmp_path: Path) -> None:
    raw = b"original source"
    (tmp_path / "input").write_bytes(raw)
    spec = {
        "path": "input",
        "sha256": digest(raw),
        "sha512": hashlib.sha512(raw).hexdigest(),
        "git_blob": hashlib.sha1(b"blob 15\0" + raw).hexdigest(),
    }
    assert read_source(tmp_path, spec, False) == raw
    (tmp_path / "input").write_bytes(b"tampered source")
    with pytest.raises(ValueError, match="SHA-256"):
        read_source(tmp_path, spec, False)


def test_recipe_coverage_cannot_skip_an_input() -> None:
    raw = b"patch bytes"
    checksum = hashlib.sha512(raw).hexdigest()
    recipe = (
        'pkgname=sample\npkgver=1.0\npkgrel=2\nsha512sums="\n' + checksum + '  fix.patch\n"\n'
    ).encode()
    origin = {
        "name": "sample",
        "version": "1.0-r2",
        "recipe_path": "aports/sample/APKBUILD",
        "checksum_inputs": [{"kind": "aport", "name": "fix.patch", "sha512": checksum}],
    }
    files = {"aports/sample/APKBUILD": recipe, "aports/sample/fix.patch": raw}
    verify_recipe(origin, files)
    origin["checksum_inputs"] = []
    with pytest.raises(ValueError, match="coverage"):
        verify_recipe(origin, files)


def test_selected_header_has_exact_byte_extent() -> None:
    raw = b"/* copyright */\nprogram body"
    selection = {"start": 0, "end": 15, "sha256": digest(raw[:15])}
    assert selected_notice(raw, selection) == raw[:15]
    with pytest.raises(ValueError, match="digest"):
        selected_notice(raw, {**selection, "end": 16})


def test_notice_links_are_never_followed() -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member = tarfile.TarInfo("project/LICENSE")
        member.type, member.linkname = tarfile.SYMTYPE, "/private/file"
        archive.addfile(member)
    with pytest.raises(ValueError, match="non-regular"):
        selected_notice(buffer.getvalue(), {"member": "project/LICENSE", "sha256": "0" * 64})


def test_published_mapping_rejects_changed_origin() -> None:
    manifest = json.loads((ROOT / "third_party/alpine-68958f1/sources.json").read_text())
    verify_supplement(ROOT / "third_party/68958f1", manifest, ROOT / "third_party/68958f1-alpine")
    changed = copy.deepcopy(manifest)
    changed["origins"][0]["version"] = "999-r0"
    with pytest.raises(ValueError, match="Origin identity"):
        verify_supplement(
            ROOT / "third_party/68958f1", changed, ROOT / "third_party/68958f1-alpine"
        )
