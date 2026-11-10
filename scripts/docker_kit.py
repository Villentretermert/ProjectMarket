"""Export pinned Linux images and verify the portable kit without Docker or Git."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import IO, Any

ROLES = {"api", "bot", "db", "proxy"}
FILES = {role + ".tar" for role in ROLES} | {
    "sources.tar",
    "source-receipt.json",
    "recipe.json",
    "compose.yaml",
    "compose.local.yaml",
    "compose.images.yaml",
    "prepare.py",
    "README.md",
    "verify.py",
}
SCHEMA = "marketob-docker-kit/v1"


def checksum(stream: IO[bytes]) -> str:
    result = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        result.update(chunk)
    return result.hexdigest()


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return checksum(stream)


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def decode(raw: bytes) -> Any:
    return json.loads(raw, object_pairs_hook=unique)


def image_archive(path: Path, image_id: str) -> dict[str, int]:
    """Check our single-image tagless Docker-save profile; never extract a layer."""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Expected immutable image ID")
    with tarfile.open(path, "r:") as archive:
        members: dict[str, tarfile.TarInfo] = {}
        for member in archive:
            if member.name in members or len(members) >= 2048:
                raise ValueError("Duplicate or excessive image archive members")
            if member.isdir() and member.name in {"blobs", "blobs/sha256"}:
                members[member.name] = member
                continue
            if not member.isfile() or not 0 <= member.size <= 16 * 1024**3:
                raise ValueError("Invalid image archive member type/size")
            blob = re.fullmatch(r"blobs/sha256/([0-9a-f]{64})", member.name)
            if not blob and member.name not in {"manifest.json", "index.json", "oci-layout"}:
                raise ValueError("Unexpected image archive member")
            members[member.name] = member
            if blob:
                stream = archive.extractfile(member)
                assert stream is not None
                if checksum(stream) != blob[1]:
                    raise ValueError("Image blob digest mismatch")

        def read(name: str) -> Any:
            row = members.get(name)
            if row is None or not row.isfile() or not 0 < row.size <= 1024 * 1024:
                raise ValueError("Missing or oversized image metadata")
            stream = archive.extractfile(row)
            assert stream is not None
            return decode(stream.read())

        def descriptor(row: dict[str, Any], media_type: str) -> str:
            value = row["digest"]
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
                raise ValueError("Invalid descriptor digest")
            name = "blobs/sha256/" + value[7:]
            if (
                row.get("mediaType") != media_type
                or name not in members
                or row.get("size") != members[name].size
                or row.get("annotations")
            ):
                raise ValueError("Image descriptor mismatch or named reference")
            return str(name)

        manifest = read("manifest.json")
        if not isinstance(manifest, list) or len(manifest) != 1 or manifest[0].get("RepoTags"):
            raise ValueError("Expected exactly one tagless Docker image")
        row = manifest[0]
        config_path = "blobs/sha256/" + image_id[7:]
        if row["Config"] != config_path:
            raise ValueError("Docker image identity mismatch")
        config = read(config_path)
        if (config.get("os"), config.get("architecture")) != ("linux", "amd64"):
            raise ValueError("Expected linux/amd64 image")
        layers = row["Layers"]
        if (
            not isinstance(layers, list)
            or not layers
            or any(name not in members for name in layers)
        ):
            raise ValueError("Missing image layers")
        if config["rootfs"] != {
            "type": "layers",
            "diff_ids": ["sha256:" + n.removeprefix("blobs/sha256/") for n in layers],
        }:
            raise ValueError("Layer sequence differs from image config")
        if read("oci-layout") != {"imageLayoutVersion": "1.0.0"}:
            raise ValueError("Unexpected OCI layout")
        index = read("index.json")
        if (
            index.get("schemaVersion") != 2
            or len(index["manifests"]) != 1
            or index.get("annotations")
        ):
            raise ValueError("Expected one unnamed OCI manifest")
        oci = read(descriptor(index["manifests"][0], "application/vnd.oci.image.manifest.v1+json"))
        if (
            oci.get("schemaVersion") != 2
            or descriptor(oci["config"], "application/vnd.oci.image.config.v1+json") != config_path
        ):
            raise ValueError("OCI and Docker image identities differ")
        if [
            descriptor(layer, "application/vnd.oci.image.layer.v1.tar") for layer in oci["layers"]
        ] != layers:
            raise ValueError("OCI and Docker layer sequences differ")
        return {"members": len(members), "layers": len(layers)}


def verify(directory: Path, expected: str) -> dict[str, Any]:
    path = directory / "receipt.json"
    if (
        not re.fullmatch(r"[0-9a-f]{64}", expected)
        or path.is_symlink()
        or path.stat().st_size > 1024 * 1024
        or digest(path) != expected
    ):
        raise ValueError("Receipt SHA-256 mismatch or invalid receipt")
    receipt = decode(path.read_bytes())
    if (
        receipt["schema"] != SCHEMA
        or receipt["platform"] != "linux/amd64"
        or receipt["coverage_state"] != "partial"
        or not receipt["open_items"]
        or set(receipt["images"]) != ROLES
        or set(receipt["files"]) != FILES
        or not re.fullmatch("[0-9a-f]{40}", receipt["tooling_commit"])
        or not re.fullmatch("[0-9a-f]{40}", receipt["release_commit"])
    ):
        raise ValueError("Invalid kit identity or coverage")
    if {p.name for p in directory.iterdir()} != FILES | {"receipt.json", "SHA256SUMS"}:
        raise ValueError("Unexpected or missing kit files")
    for name, evidence in receipt["files"].items():
        target = directory / name
        if (
            set(evidence) != {"bytes", "sha256"}
            or type(evidence["bytes"]) is not int
            or not 0 <= evidence["bytes"] <= 32 * 1024**3
            or not re.fullmatch("[0-9a-f]{64}", evidence["sha256"])
            or target.is_symlink()
            or not target.is_file()
            or target.stat().st_size != evidence["bytes"]
            or digest(target) != evidence["sha256"]
        ):
            raise ValueError("Kit file mismatch: " + name)
    sums = directory / "SHA256SUMS"
    if (
        sums.is_symlink()
        or not sums.is_file()
        or sums.read_bytes().replace(b"\r\n", b"\n") != (expected + "  receipt.json\n").encode()
    ):
        raise ValueError("Invalid companion SHA256SUMS")
    recipe = decode((directory / "recipe.json").read_bytes())
    source = decode((directory / "source-receipt.json").read_bytes())
    for key in ("images", "release_commit", "open_items"):
        if receipt[key] != recipe[key] or receipt[key] != source["manifest"][key]:
            raise ValueError("Source and executable release bindings differ")
    if (
        source["sha256"] != receipt["files"]["sources.tar"]["sha256"]
        or source["bytes"] != receipt["files"]["sources.tar"]["bytes"]
    ):
        raise ValueError("Source archive differs from source receipt")
    for role, image_id in receipt["images"].items():
        image_archive(directory / (role + ".tar"), image_id)
    return dict(receipt)


def build(output: Path, source_directory: Path, distribution: str | None) -> str:
    from scripts.delivery_bundle import ROOT, check_recipe
    from scripts.delivery_bundle import verify as verify_source

    if output.exists() or not output.is_relative_to(ROOT / ".local"):
        raise ValueError("Use a new directory below the repository .local")
    recipe_path = "third_party/delivery-schema-20261109/recipe.json"
    recipe = check_recipe(recipe_path=recipe_path)
    # Trust the published source receipt, not a receipt supplied alongside an arbitrary tar.
    receipt_path = "docs/task-results/assets/PM-023/handover-schema-20261109/receipt.json"
    source = decode((ROOT / receipt_path).read_bytes())
    source_path = source_directory / source["archive"]
    verified = verify_source(source_path, source["sha256"])
    if any(verified[k] != recipe[k] for k in ("images", "release_commit", "open_items")):
        raise ValueError("Source kit does not belong to this release")
    if subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT
    ).strip():
        raise ValueError("Commit tracked changes before building the kit")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    prefix = ["wsl", "-d", distribution, "--exec"] if distribution else []
    output.mkdir(parents=True)
    for role, image_id in recipe["images"].items():
        destination = output / (role + ".tar")
        target = (
            subprocess.check_output(
                prefix + ["wslpath", "-a", str(destination)], encoding="utf-8"
            ).strip()
            if distribution
            else str(destination)
        )
        subprocess.run(
            prefix + ["docker", "image", "save", "--output", target, image_id], check=True
        )
        image_archive(destination, image_id)
        print("Exported and checked " + role, flush=True)
    shutil.copyfile(source_path, output / "sources.tar")
    tracked = {
        "source-receipt.json": receipt_path,
        "recipe.json": recipe_path,
        "compose.yaml": "compose.yaml",
        "compose.local.yaml": "deploy/compose.local.yaml",
        "prepare.py": "scripts/prepare_delivery.py",
        "verify.py": "scripts/docker_kit.py",
        "README.md": "docs/setup/DOCKER_KIT.md",
    }
    for name, original in tracked.items():
        (output / name).write_bytes(
            subprocess.check_output(["git", "show", commit + ":" + original], cwd=ROOT)
        )
    lines = ["services:"]
    for service, role in {
        "api": "api",
        "migrate": "api",
        "maintenance": "api",
        "db": "db",
        "proxy": "proxy",
    }.items():
        lines += [
            f"  {service}:",
            "    image: " + json.dumps(recipe["images"][role]),
            "    build: !reset null",
            "    pull_policy: never",
        ]
        if service == "proxy":
            lines += ['    ports: !override ["127.0.0.1:${MARKETOB_HTTPS_PORT:-18443}:8443"]']
    (output / "compose.images.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    receipt = {
        "schema": SCHEMA,
        "platform": "linux/amd64",
        "tooling_commit": commit,
        "release_commit": recipe["release_commit"],
        "images": recipe["images"],
        "coverage_state": "partial",
        "open_items": recipe["open_items"],
        "files": {
            name: {"bytes": (output / name).stat().st_size, "sha256": digest(output / name)}
            for name in sorted(FILES)
        },
    }
    path = output / "receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    expected = digest(path)
    (output / "SHA256SUMS").write_text(expected + "  receipt.json\n", encoding="ascii")
    verify(output, expected)
    return expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--wsl")
    args = parser.parse_args()
    if args.verify and args.sha256:
        value = verify(args.verify.resolve(), args.sha256)
        print(
            json.dumps(
                {
                    "integrity": "verified",
                    "images": len(value["images"]),
                    "platform": value["platform"],
                    "coverage_state": value["coverage_state"],
                }
            )
        )
    elif args.output and args.sources:
        print(
            json.dumps(
                {"receipt_sha256": build(args.output.resolve(), args.sources.resolve(), args.wsl)}
            )
        )
    else:
        parser.error("Choose --verify/--sha256 or --output/--sources")


if __name__ == "__main__":
    main()
