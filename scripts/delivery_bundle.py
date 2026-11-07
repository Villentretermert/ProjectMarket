"""Assemble collected source materials; verify a handover tar without Git or network."""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import IO, Any

ROOT = Path(__file__).resolve().parents[1]
RECIPE = "third_party/delivery-68958f1/recipe.json"
SCHEMA = "marketob-source-handover/v1"
BLOCK = 1024 * 1024


def stream_hash(stream: IO[bytes]) -> str:
    hasher = hashlib.sha256()
    while block := stream.read(BLOCK):
        hasher.update(block)
    return hasher.hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return stream_hash(stream)


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def json_object(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def safe_name(name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_./-]{1,100}", name) or any(
        p in ("", ".", "..") for p in name.split("/")
    ):
        raise ValueError("Unsafe archive member name")


def file_table(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if (
        manifest.get("schema_version") != SCHEMA
        or manifest.get("coverage_state") != "partial"
        or not manifest.get("open_items")
        or not re.fullmatch("[0-9a-f]{40}", manifest.get("release_commit", ""))
        or not re.fullmatch("[0-9a-f]{40}", manifest.get("tooling_commit", ""))
        or set(manifest.get("images", {})) != {"api", "bot", "db", "proxy"}
        or any(not re.fullmatch("sha256:[0-9a-f]{64}", v) for v in manifest["images"].values())
    ):
        raise ValueError("Invalid manifest identity or coverage")
    rows = manifest.get("files", [])
    if not isinstance(rows, list) or not 1 <= len(rows) <= 128:
        raise ValueError("Invalid file count")
    expected = {}
    for row in rows:
        name = row["name"]
        safe_name(name)
        if (
            name == "manifest.json"
            or name in expected
            or type(row["size"]) is not int
            or not 0 <= row["size"] <= 4 * 1024**3
            or not re.fullmatch("[0-9a-f]{64}", row["sha256"])
        ):
            raise ValueError("Invalid or repeated manifest file")
        expected[name] = row
    return expected


def verify(path: Path, expected_sha256: str) -> dict[str, Any]:
    """Bind the entire tar, including its manifest, to an external trusted digest."""
    if not re.fullmatch("[0-9a-f]{64}", expected_sha256):
        raise ValueError("Expected a lowercase SHA-256 from the delivery receipt")
    if file_hash(path) != expected_sha256:
        raise ValueError("Whole archive SHA-256 mismatch")
    # No extraction or execution. Limit manifest allocation before decoding JSON.
    with tarfile.open(path, "r|") as archive:
        first = archive.next()
        if (
            first is None
            or first.name != "manifest.json"
            or not first.isfile()
            or not 0 < first.size <= 256 * 1024
        ):
            raise ValueError("Expected a bounded manifest as the first member")
        source = archive.extractfile(first)
        assert source is not None
        manifest = json_object(source.read())
        expected = file_table(manifest)
        seen = set()
        for member in archive:
            if member is first:
                continue
            row = expected.get(member.name)
            if (
                not member.isfile()
                or row is None
                or member.name in seen
                or member.size != row["size"]
            ):
                raise ValueError("Unexpected, duplicate or invalid archive member")
            source = archive.extractfile(member)
            assert source is not None
            if stream_hash(source) != row["sha256"]:
                raise ValueError("Member SHA-256 mismatch: " + member.name)
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError("Missing archive members")
    return manifest


def pack(destination: Path, files: dict[str, Path], identity: dict[str, Any]) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(destination)
    manifest = identity | {
        "schema_version": SCHEMA,
        "files": [
            {"name": name, "size": path.stat().st_size, "sha256": file_hash(path)}
            for name, path in sorted(files.items())
        ],
    }
    file_table(manifest)
    raw = (json.dumps(manifest, indent=2, ensure_ascii=True) + "\n").encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        pending = Path(temporary.name)
    try:
        with tarfile.open(pending, "w", format=tarfile.GNU_FORMAT) as archive:
            header = tarfile.TarInfo("manifest.json")
            header.size, header.mode = len(raw), 0o644
            archive.addfile(header, io.BytesIO(raw))
            for row in manifest["files"]:
                header = tarfile.TarInfo(row["name"])
                header.size, header.mode = row["size"], 0o644
                with files[row["name"]].open("rb") as stream:
                    archive.addfile(header, stream)
        checksum = file_hash(pending)
        verify(pending, checksum)
        # Windows rename refuses an existing target; POSIX link provides that guarantee.
        if os.name == "nt":
            os.rename(pending, destination)
        else:
            os.link(pending, destination)
    finally:
        pending.unlink(missing_ok=True)
    return {"sha256": checksum, "bytes": destination.stat().st_size, "manifest": manifest}


def check_recipe(root: Path = ROOT) -> dict[str, Any]:
    recipe = json_object((root / RECIPE).read_bytes())
    for name, checksum in recipe["bound_files"].items():
        safe_name(name)
        if file_hash(root / name) != checksum:
            raise ValueError("Release evidence changed: " + name)
    inventory = json_object((root / "third_party/68958f1-native/inventory.json").read_bytes())
    actual = {i["role"]: i["id"] for i in inventory["images"]}
    if (
        actual != recipe["images"]
        or inventory["release"] != recipe["release_commit"][:7]
        or set(actual) != {"api", "bot", "db", "proxy"}
        or not recipe["open_items"]
    ):
        raise ValueError("Recipe does not match the installed release")
    names = set()
    for entry in recipe["sources"]:
        safe_name(entry["name"])
        if entry["name"] in names or not re.fullmatch("[0-9a-f]{64}", entry["sha256"]):
            raise ValueError("Invalid source entry")
        names.add(entry["name"])
    return recipe


def build(output: Path, inputs: dict[str, Path]) -> dict[str, Any]:
    if output.exists() or not output.resolve().is_relative_to(ROOT / ".local"):
        raise ValueError("Use a new output directory below the repository's .local")
    recipe = check_recipe()
    expected = {r["name"]: r for r in recipe["sources"]}
    if set(inputs) != set(expected):
        raise ValueError("Supply each source archive from the recipe exactly once")
    for name, path in inputs.items():
        if (
            path.stat().st_size != expected[name]["size"]
            or file_hash(path) != expected[name]["sha256"]
        ):
            raise ValueError("Source archive differs from reviewed receipt: " + name)

    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", *args], cwd=ROOT)

    if git("status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError("Commit tracked changes before assembling a versioned handover")
    tooling = git("rev-parse", "HEAD").decode().strip()
    if git("show", "HEAD:" + RECIPE) != (ROOT / RECIPE).read_bytes():
        raise ValueError("Recipe bytes must match the tooling commit")
    output.mkdir(parents=True)
    stage = output / "staging"
    stage.mkdir()
    files = {"sources/" + name: path for name, path in inputs.items()}
    # Git objects exclude .env, backups, credentials and other untracked local data.
    for label, revision in (("project", recipe["release_commit"]), ("tooling", tooling)):
        target = stage / f"{label}.tar"
        subprocess.run(
            ["git", "archive", "--format=tar", "--output", str(target), revision],
            cwd=ROOT,
            check=True,
        )
        files["sources/" + label + ".tar"] = target
    for name, tracked in {
        "README.md": "docs/licensing/SOURCE_HANDOVER.md",
        "GAPS.md": "third_party/delivery-68958f1/GAPS.md",
        "LICENSE": "LICENSE",
        "NOTICE": "NOTICE",
        "verify_bundle.py": "scripts/delivery_bundle.py",
    }.items():
        target = stage / name
        target.write_bytes(git("show", tooling + ":" + tracked))
        files[name] = target
    result = pack(
        output / "marketob-sources-68958f1.tar",
        files,
        {
            "release_commit": recipe["release_commit"],
            "tooling_commit": tooling,
            "images": recipe["images"],
            "coverage_state": "partial",
            "open_items": recipe["open_items"],
            "source_scope": recipe["sources"],
        },
    )
    result["archive"] = "marketob-sources-68958f1.tar"
    (output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (output / "SHA256SUMS").write_text(result["sha256"] + "  " + result["archive"] + "\n")
    for name in ("README.md", "verify_bundle.py"):
        shutil.copyfile(stage / name, output / name)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--check-recipe", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source", action="append", default=[], metavar="NAME=PATH")
    args = parser.parse_args()
    if args.verify:
        if not args.sha256:
            parser.error("--verify requires the SHA-256 from the published receipt")
        manifest = verify(args.verify, args.sha256)
        print(
            json.dumps(
                {
                    "integrity": "verified",
                    "files": len(manifest["files"]),
                    "coverage_state": manifest["coverage_state"],
                    "open_items": manifest["open_items"],
                }
            )
        )
    elif args.check_recipe:
        recipe = check_recipe()
        print(json.dumps({"recipe": "verified", "source_archives": len(recipe["sources"])}))
    elif args.output:
        inputs = {}
        for item in args.source:
            name, separator, path = item.partition("=")
            if not separator or name in inputs:
                parser.error("Use each NAME=PATH once")
            inputs[name] = Path(path).resolve()
        result = build(args.output.resolve(), inputs)
        print(json.dumps({k: v for k, v in result.items() if k != "manifest"}))
    else:
        parser.error("Select --verify, --check-recipe or --output")


if __name__ == "__main__":
    main()
