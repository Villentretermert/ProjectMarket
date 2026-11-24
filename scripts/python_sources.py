"""Collect locked runtime sdists; verify a source supplement with only Python stdlib.

No package code is executed or extracted. A sdist/version match is not evidence
of binary reproducibility or a complete offline build dependency closure.
"""

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
import tomllib
import urllib.parse
import urllib.request
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = "third_party/schema-20261109/inventory.json"
RECIPE = "third_party/delivery-schema-20261109/recipe.json"
MANIFEST = "third_party/python-sources-schema-20261109/manifest.json"
SCHEMA = "marketob-python-sources/v1"
LIMIT = 100_000_000
CONTEXT = {"inventory.json", "uv.lock", "manifest.json", "verify.py"}
GAPS = [
    "build-dependencies",
    "cpython-and-go-inputs",
    "native-link-and-rebuild",
    "release-acceptance",
]


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def object_json(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, value in items:
            if name in result:
                raise ValueError("Duplicate JSON key")
            result[name] = value
        return result

    result = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(result, dict):
        raise ValueError("Expected JSON object")
    return result


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or ":" in name
        or str(path) != name
    ):
        raise ValueError("Unsafe or noncanonical archive path")
    return name


def source_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "files.pythonhosted.org"
        or not parsed.path.startswith("/packages/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Expected pinned PyPI source URL")
    filename = safe_name(parsed.path.rsplit("/", 1)[-1])
    if not filename.endswith(".tar.gz"):
        raise ValueError("Unsupported sdist format")
    return filename


def plan(inventory_raw: bytes, lock_raw: bytes, release: str) -> dict[str, Any]:
    inventory = object_json(inventory_raw)
    images = {row["role"]: row for row in inventory["images"]}
    if len(images) != len(inventory["images"]) or set(images) != {"api", "bot", "db", "proxy"}:
        raise ValueError("Expected four distinct image roles")
    if not re.fullmatch(r"[0-9a-f]{40}", release):
        raise ValueError("Expected immutable release commit")
    for image in images.values():
        if (
            not re.fullmatch(r"sha256:[0-9a-f]{64}", image["id"])
            or image["os"] != "linux"
            or image["architecture"] != "amd64"
        ):
            raise ValueError("Unexpected image identity or platform")
    packages = tomllib.loads(lock_raw.decode("utf-8"))["package"]
    locked = {normalized(p["name"]): p for p in packages}
    if len(locked) != len(packages):
        raise ValueError("Ambiguous locked package")
    selected: dict[str, dict[str, Any]] = {}
    for role, image in sorted(images.items()):
        seen = set()
        for package in image["components"]:
            if package["ecosystem"] != "pypi":
                continue
            if role not in {"api", "bot"}:
                raise ValueError("Unexpected Python image role")
            name, version = normalized(package["name"]), package["version"]
            if name in seen:
                raise ValueError("Duplicate installed package")
            seen.add(name)
            pin = locked.get(name)
            if not pin or pin["version"] != version or "sdist" not in pin:
                raise ValueError("Installed package has no matching locked sdist: " + name)
            if pin["source"] != {"registry": "https://pypi.org/simple"}:
                raise ValueError("Expected registry package")
            sdist = pin["sdist"]
            filename = source_url(sdist["url"])
            if (
                not re.fullmatch(r"sha256:[0-9a-f]{64}", sdist["hash"])
                or type(sdist["size"]) is not int
                or not 0 < sdist["size"] <= LIMIT
            ):
                raise ValueError("Invalid locked sdist size or hash")
            row = selected.setdefault(
                name,
                {
                    "name": name,
                    "version": version,
                    "path": "sdists/" + filename,
                    "url": sdist["url"],
                    "size": sdist["size"],
                    "sha256": sdist["hash"][7:],
                    "images": {},
                },
            )
            if row["version"] != version:
                raise ValueError("Conflicting installed versions")
            row["images"][role] = image["id"]
    if not selected or {r for p in selected.values() for r in p["images"]} != {"api", "bot"}:
        raise ValueError("Empty Python runtime coverage")
    if len({s["path"] for s in selected.values()}) != len(selected):
        raise ValueError("Colliding source filenames")
    return {
        "schema": SCHEMA,
        "release_commit": release,
        "coverage_state": "partial",
        "open_items": GAPS,
        "images": {role: image["id"] for role, image in sorted(images.items())},
        "inventory_sha256": digest(inventory_raw),
        "lock_sha256": digest(lock_raw),
        "inputs": [selected[name] for name in sorted(selected)],
    }


def validate_sdist(raw: bytes, spec: dict[str, Any]) -> dict[str, str]:
    if len(raw) != spec["size"] or digest(raw) != spec["sha256"]:
        raise ValueError("Sdist size or SHA-256 mismatch: " + spec["name"])
    metadata = []
    expanded = 0
    seen: set[str] = set()
    # Stream headers: cap member count/expanded data; never unpack or run setup.py.
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r|gz") as archive:
        for index, member in enumerate(archive):
            name = safe_name(member.name.rstrip("/") if member.isdir() else member.name)
            if name in seen or index >= 50_000:
                raise ValueError("Duplicate or excessive sdist members")
            seen.add(name)
            # Preserve upstream links as opaque archive data; never follow them.
            if not (member.isdir() or member.isfile() or member.issym() or member.islnk()):
                raise ValueError("Unsupported sdist member type")
            expanded += member.size
            if member.size > LIMIT or expanded > 500_000_000:
                raise ValueError("Oversized sdist contents")
            path = PurePosixPath(name)
            if len(path.parts) == 2 and path.name == "PKG-INFO":
                if not member.isfile() or member.size > 4_000_000:
                    raise ValueError("Invalid PKG-INFO member")
                stream = archive.extractfile(member)
                assert stream is not None
                metadata.append(stream.read())
    if len(metadata) != 1:
        raise ValueError("Expected one root PKG-INFO")
    headers = BytesParser().parsebytes(metadata[0], headersonly=True)
    names, versions = headers.get_all("Name", []), headers.get_all("Version", [])
    if len(names) != 1 or len(versions) != 1:
        raise ValueError("Ambiguous PKG-INFO identity")
    if normalized(names[0]) != spec["name"] or versions[0] != spec["version"]:
        raise ValueError("PKG-INFO differs from installed identity")
    return {
        "name": spec["name"],
        "version": spec["version"],
        "metadata_sha256": digest(metadata[0]),
    }


def verify(archive_path: Path, expected_sha256: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Expected external archive SHA-256")
    if archive_path.stat().st_size > 1_000_000_000 or file_digest(archive_path) != expected_sha256:
        raise ValueError("Archive SHA-256 or size mismatch")
    with tarfile.open(archive_path, mode="r:") as archive:
        members = {}
        for index, member in enumerate(archive):
            name = safe_name(member.name)
            if index >= 200 or name in members or not member.isfile() or member.size > LIMIT:
                raise ValueError("Invalid source supplement member")
            members[name] = member

        def read(name: str) -> bytes:
            stream = archive.extractfile(members[name])
            assert stream is not None
            return stream.read()

        if not CONTEXT <= members.keys():
            raise ValueError("Missing supplement context")
        manifest = object_json(read("manifest.json"))
        expected = plan(read("inventory.json"), read("uv.lock"), manifest["release_commit"])
        if manifest != expected:
            raise ValueError("Source coverage or provenance differs from inventory/lock")
        if set(members) != CONTEXT | {p["path"] for p in manifest["inputs"]}:
            raise ValueError("Missing or unexpected supplement files")
        verified = [validate_sdist(read(p["path"]), p) for p in manifest["inputs"]]
    return {
        "archive_sha256": expected_sha256,
        "archive_bytes": archive_path.stat().st_size,
        "release_commit": manifest["release_commit"],
        "images": manifest["images"],
        "coverage_state": "partial",
        "open_items": manifest["open_items"],
        "verified_sdists": verified,
    }


def repository_context() -> tuple[dict[str, Any], dict[str, bytes]]:
    recipe = object_json((ROOT / RECIPE).read_bytes())
    inventory = (ROOT / INVENTORY).read_bytes()
    if digest(inventory) != recipe["bound_files"][INVENTORY]:
        raise ValueError("Inventory differs from delivery binding")
    lock = subprocess.check_output(["git", "show", recipe["release_commit"] + ":uv.lock"], cwd=ROOT)
    manifest = plan(inventory, lock, recipe["release_commit"])
    if manifest["images"] != recipe["images"]:
        raise ValueError("Images differ from delivery recipe")
    if object_json((ROOT / MANIFEST).read_bytes()) != manifest:
        raise ValueError("Published source plan changed")
    return manifest, {"inventory.json": inventory, "uv.lock": lock}


def collect(output: Path, cache: Path, fetch: bool) -> dict[str, Any]:
    manifest, context = repository_context()
    output.mkdir(parents=True, exist_ok=False)
    cache.mkdir(parents=True, exist_ok=True)
    archive_path = output / "python-runtime-sources.tar"
    context["manifest.json"] = (ROOT / MANIFEST).read_bytes()
    context["verify.py"] = Path(__file__).read_bytes()
    try:
        with tarfile.open(archive_path, mode="x:") as archive:

            def add(name: str, raw: bytes) -> None:
                member = tarfile.TarInfo(name)
                member.size, member.mode = len(raw), 0o644
                archive.addfile(member, io.BytesIO(raw))

            for name, raw in sorted(context.items()):
                add(name, raw)
            for spec in manifest["inputs"]:
                cached = cache / spec["sha256"]
                if cached.is_symlink():
                    raise ValueError("Source cache link is not allowed")
                if not cached.exists() and fetch:
                    request = urllib.request.Request(
                        spec["url"], headers={"User-Agent": "MarkeTOB-sources/1"}
                    )
                    with urllib.request.urlopen(request, timeout=30) as response:
                        source_url(response.url)
                        raw = response.read(spec["size"] + 1)
                    validate_sdist(raw, spec)
                    with cached.open("xb") as stream:
                        stream.write(raw)
                if cached.stat().st_size != spec["size"]:
                    raise ValueError("Cached sdist size mismatch")
                raw = cached.read_bytes()
                validate_sdist(raw, spec)
                add(spec["path"], raw)
        receipt = verify(archive_path, file_digest(archive_path))
        (output / "verify.py").write_bytes(context["verify.py"])
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        (output / "SHA256SUMS").write_text(
            receipt["archive_sha256"] + "  " + archive_path.name + "\n", encoding="ascii"
        )
        return receipt
    except Exception:
        (output / "INCOMPLETE.txt").write_text("Incomplete collection; do not distribute.\n")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", type=Path)
    mode.add_argument("--collect", type=Path)
    mode.add_argument("--check-plan", action="store_true")
    parser.add_argument("--sha256")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--cache", type=Path, default=ROOT / ".local/python-sdist-cache")
    args = parser.parse_args()
    if args.verify:
        if not args.sha256:
            parser.error("--verify requires an independently supplied --sha256")
        result = verify(args.verify, args.sha256)
    elif args.collect:
        for path in (args.collect, args.cache):
            if (
                not path.resolve().is_relative_to(ROOT / ".local")
                or path.resolve() == ROOT / ".local"
            ):
                parser.error("Collection output/cache must be below repository .local")
        result = collect(args.collect, args.cache, args.fetch)
    else:
        manifest, _ = repository_context()
        result = {"planned_sdists": len(manifest["inputs"]), "coverage_state": "partial"}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
