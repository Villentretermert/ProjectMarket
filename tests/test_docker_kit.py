"""Portable delivery rejects changed bytes, image references and release mismatches."""

import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

from scripts.docker_kit import FILES, ROLES, SCHEMA, digest, image_archive, verify
from scripts.prepare_delivery import prepare


def raw(value: Any) -> bytes:
    return json.dumps(value).encode()


def make_image(path: Path, fault: str = "") -> str:
    entries: dict[str, bytes] = {}

    def blob(data: bytes, media: str) -> dict[str, Any]:
        checksum = hashlib.sha256(data).hexdigest()
        entries["blobs/sha256/" + checksum] = data
        return {"digest": "sha256:" + checksum, "size": len(data), "mediaType": media}

    layer = blob(b"synthetic layer bytes", "application/vnd.oci.image.layer.v1.tar")
    config = blob(
        raw(
            {
                "os": "linux",
                "architecture": "arm64" if fault == "platform" else "amd64",
                "rootfs": {"type": "layers", "diff_ids": [layer["digest"]]},
            }
        ),
        "application/vnd.oci.image.config.v1+json",
    )
    layer_path = "blobs/sha256/" + layer["digest"][7:]
    config_path = "blobs/sha256/" + config["digest"][7:]
    oci = {"schemaVersion": 2, "config": config, "layers": [layer]}
    if fault == "oci_identity":
        oci["config"] = layer
    manifest = blob(raw(oci), "application/vnd.oci.image.manifest.v1+json")
    if fault == "oci_tag":
        manifest["annotations"] = {"org.opencontainers.image.ref.name": "existing:tag"}
    docker = [{"Config": config_path, "RepoTags": None, "Layers": [layer_path]}]
    if fault == "tag":
        docker[0]["RepoTags"] = ["existing:tag"]
    if fault == "extra_image":
        docker.append(docker[0])
    entries.update(
        {
            "manifest.json": raw(docker),
            "index.json": raw({"schemaVersion": 2, "manifests": [manifest]}),
            "oci-layout": raw({"imageLayoutVersion": "1.0.0"}),
        }
    )
    if fault == "corrupt_layer":
        entries[layer_path] = b"changed"
    if fault == "missing_layer":
        del entries[layer_path]
    if fault == "path":
        entries["../outside"] = b"unexpected"
    with tarfile.open(path, "w") as archive:
        for name, data in entries.items():
            item = tarfile.TarInfo(name)
            item.size = len(data)
            if fault == "symlink" and name == layer_path:
                item.type, item.linkname, item.size = tarfile.SYMTYPE, "/outside", 0
            archive.addfile(item, io.BytesIO(data))
        if fault == "duplicate":
            archive.addfile(item, io.BytesIO(data))
    return str(config["digest"])


@pytest.mark.parametrize(
    "fault",
    [
        "tag",
        "oci_tag",
        "oci_identity",
        "extra_image",
        "corrupt_layer",
        "missing_layer",
        "path",
        "symlink",
        "duplicate",
        "platform",
    ],
)
def test_invalid_image_export(tmp_path: Path, fault: str) -> None:
    path = tmp_path / "image.tar"
    expected = make_image(path, fault)
    with pytest.raises(ValueError):
        image_archive(path, expected)


def test_image_id_is_not_a_mutable_tag(tmp_path: Path) -> None:
    path = tmp_path / "image.tar"
    expected = make_image(path)
    assert image_archive(path, expected)["layers"] == 1
    with pytest.raises(ValueError, match="identity mismatch"):
        image_archive(path, "sha256:" + "0" * 64)


def write_receipt(directory: Path, value: dict[str, Any]) -> str:
    (directory / "receipt.json").write_bytes(raw(value))
    checksum = digest(directory / "receipt.json")
    (directory / "SHA256SUMS").write_text(checksum + "  receipt.json\n")
    return checksum


def kit(directory: Path) -> tuple[dict[str, Any], str]:
    for name in FILES:
        (directory / name).write_bytes(b"fixture")
    images = {role: make_image(directory / (role + ".tar")) for role in ROLES}
    identity = {"images": images, "release_commit": "a" * 40, "open_items": ["still-open"]}
    (directory / "recipe.json").write_bytes(raw(identity))
    (directory / "source-receipt.json").write_bytes(
        raw(
            {
                "manifest": identity,
                "sha256": digest(directory / "sources.tar"),
                "bytes": (directory / "sources.tar").stat().st_size,
            }
        )
    )
    shutil.copyfile(
        Path(__file__).resolve().parents[1] / "scripts/docker_kit.py", directory / "verify.py"
    )
    value = identity | {
        "schema": SCHEMA,
        "platform": "linux/amd64",
        "tooling_commit": "b" * 40,
        "coverage_state": "partial",
        "files": {
            name: {"bytes": (directory / name).stat().st_size, "sha256": digest(directory / name)}
            for name in FILES
        },
    }
    return value, write_receipt(directory, value)


def test_standalone_verifier_without_checkout(tmp_path: Path) -> None:
    _, expected = kit(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(tmp_path / "verify.py"),
            "--verify",
            str(tmp_path),
            "--sha256",
            expected,
        ],
        cwd=tmp_path,
        capture_output=True,
        check=True,
        text=True,
        timeout=20,
    )
    assert json.loads(result.stdout)["integrity"] == "verified"


@pytest.mark.parametrize(
    "fault", ["receipt", "file", "missing", "extra", "source_binding", "coverage"]
)
def test_kit_rejects_wrong_receipt_or_contents(tmp_path: Path, fault: str) -> None:
    value, expected = kit(tmp_path)
    if fault == "receipt":
        expected = "0" * 64
    elif fault == "file":
        (tmp_path / "compose.yaml").write_bytes(b"changed")
    elif fault == "missing":
        (tmp_path / "db.tar").unlink()
    elif fault == "extra":
        (tmp_path / ".env").write_bytes(b"not part of a kit")
    else:
        value["release_commit" if fault == "source_binding" else "coverage_state"] = (
            "c" * 40 if fault == "source_binding" else "complete"
        )
        expected = write_receipt(tmp_path, value)
    with pytest.raises(ValueError):
        verify(tmp_path, expected)


def test_prepare_isolated_credentials_without_overwrite(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    assert prepare(first, 18000, 18443) != prepare(second, 18000, 18443)
    original = (first / ".env").read_bytes()
    assert original != (second / ".env").read_bytes()
    assert b"http://127.0.0.1:18000" in original
    with pytest.raises(FileExistsError):
        prepare(first, 18001, 18444)
    assert (first / ".env").read_bytes() == original


@pytest.mark.parametrize("ports", [(80, 8443), (18000, 18000), (18000, 65536)])
def test_prepare_rejects_invalid_ports_before_writing(
    tmp_path: Path, ports: tuple[int, int]
) -> None:
    path = tmp_path / "run"
    with pytest.raises(ValueError):
        prepare(path, *ports)
    assert not path.exists()
