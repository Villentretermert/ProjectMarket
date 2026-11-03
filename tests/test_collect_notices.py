"""The notice collector must preserve evidence and reject misleading bundles."""

import io
import json
import tarfile
from pathlib import Path

import pytest

from scripts.collect_notices import (
    Collector,
    apk_components,
    digest,
    go_modules,
    notice_files,
    pinned_source_notices,
    verify_bundle,
    write_bundle,
)


def archive_with(name: str, content: bytes = b"license", link: str = "") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member = tarfile.TarInfo(name)
        if link:
            member.type, member.linkname = tarfile.LNKTYPE, link
            archive.addfile(member)
        else:
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return buffer.getvalue()


@pytest.mark.parametrize("name", ["../LICENSE", "/etc/LICENSE", "texts/../../LICENSE"])
def test_archive_never_escapes_output(name: str) -> None:
    with pytest.raises(ValueError, match="Unsafe archive path"):
        notice_files(archive_with(name))


def test_archive_rejects_external_hardlink() -> None:
    with pytest.raises(ValueError, match="Unsafe archive link"):
        notice_files(archive_with("usr/share/doc/test/copyright", link="/private/LICENSE"))


def test_debian_license_reference_and_copyright_bytes() -> None:
    text = b"Full GPL text\r\n"
    name = "usr/share/common-licenses/GPL-3"
    assert notice_files(archive_with(name, text)) == {name: text}
    assert notice_files(archive_with("usr/share/doc/test/changelog", b"ignored")) == {}


def test_apk_license_cannot_be_replaced_by_file_record() -> None:
    rows = apk_components(
        "P:busybox\nV:1.0-r1\nL:GPL-2.0-only\no:busybox\nF:etc\nR:config\nL:symlink-data\n"
    )
    assert rows[0]["declared_license"] == "GPL-2.0-only"
    assert rows[0]["notices"] == []


def test_go_replacement_requires_explicit_mapping() -> None:
    with pytest.raises(ValueError, match="replacements"):
        go_modules(
            "/out/caddy: go1.26.10\n\tdep\tx/y\tv1.0.0\th1:example\n\t=>\tx/z\tv1.1.0\th1:other\n"
        )


def test_builder_must_match_shipped_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    collector = Collector(None)
    monkeypatch.setattr(collector, "identity", lambda _: {"id": "builder"})
    monkeypatch.setattr(collector, "run", lambda image, *_: image.encode() + b" /binary")
    with pytest.raises(ValueError, match="does not match"):
        collector.go("runtime", "builder", "/usr/bin/caddy")


def test_bundle_integrity_and_unresolved_gap(tmp_path: Path) -> None:
    collector = Collector(None)
    record = collector.record("package/LICENSE", b"License text\n")
    report = {"notices": [record], "gaps": [{"name": "missing"}]}
    write_bundle(tmp_path, report, collector.texts)
    verify_bundle(tmp_path)
    assert json.loads((tmp_path / "inventory.json").read_text())["gaps"] == [{"name": "missing"}]
    raw = tmp_path / "texts.tar.gz"
    original = raw.read_bytes()
    raw.write_bytes(original + b"tampered")
    with pytest.raises(ValueError, match="Archive digest"):
        verify_bundle(tmp_path)
    raw.write_bytes(original)
    report["notices"][0]["sha256"] = "0" * 64
    (tmp_path / "inventory.json").write_text(json.dumps(report))
    with pytest.raises(ValueError, match="Broken notice"):
        verify_bundle(tmp_path)


def test_even_rehashed_bundle_rejects_unsafe_members(tmp_path: Path) -> None:
    raw = archive_with("../../outside")
    (tmp_path / "texts.tar.gz").write_bytes(raw)
    (tmp_path / "inventory.json").write_text(json.dumps({"texts_archive_sha256": digest(raw)}))
    with pytest.raises(ValueError, match="Unexpected bundle member"):
        verify_bundle(tmp_path)


def test_source_must_match_locked_archive(tmp_path: Path) -> None:
    raw = archive_with("example-1.0/LICENSE", b"MIT text")
    source = {
        "url": "https://files.pythonhosted.org/example-1.0.tar.gz",
        "hash": "sha256:" + digest(raw),
    }
    path = tmp_path / "example-1.0.tar.gz"
    path.write_bytes(raw)
    assert pinned_source_notices(source, tmp_path) == {"example-1.0/LICENSE": b"MIT text"}
    path.write_bytes(raw + b"changed")
    with pytest.raises(ValueError, match="does not match uv.lock"):
        pinned_source_notices(source, tmp_path)
