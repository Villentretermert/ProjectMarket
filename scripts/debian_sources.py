"""Verify and assemble Debian sources for the installed pilot package versions."""

import argparse
import concurrent.futures
import gzip
import hashlib
import io
import json
import lzma
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from email.parser import Parser
from pathlib import Path
from typing import Any

from scripts.alpine_notices import safe_path
from scripts.collect_notices import ROOT, digest

BASE = ROOT / "third_party/68958f1-native/inventory.json"
EVIDENCE = ROOT / "third_party/debian-68958f1"
BLOCK = 1024 * 1024


def validate_name(name: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.+_~-]*", name):
        raise ValueError(f"Unsafe package filename {name!r}")


def checked(path: Path, spec: dict[str, Any]) -> bool:
    if path.stat().st_size != spec["size"]:
        return False
    with path.open("rb") as stream:
        expected_hash: str = spec["sha256"]
        return hashlib.file_digest(stream, "sha256").hexdigest() == expected_hash


def obtain(cache: Path, name: str, spec: dict[str, Any], urls: list[str], fetch: bool) -> Path:
    path = safe_path(cache, name)
    if path.exists():
        if not checked(path, spec):
            raise ValueError(f"Cached bytes differ: {name}")
        return path
    if not fetch:
        raise FileNotFoundError(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    for url in urls:
        if not url.startswith("https://"):
            raise ValueError("Only HTTPS downloads are supported")
        for attempt in range(2):
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
                partial = Path(tmp.name)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "MarkeTOB-source-kit/1"})
                with (
                    urllib.request.urlopen(req, timeout=60) as response,
                    partial.open("wb") as dest,
                ):
                    remaining = spec["size"]
                    while block := response.read(min(BLOCK, remaining + 1)):
                        remaining -= len(block)
                        if remaining < 0:
                            raise ValueError("Oversized response")
                        dest.write(block)
                if not checked(partial, spec):
                    raise ValueError("Wrong size or SHA-256")
                os.replace(partial, path)
                return path
            except (OSError, ValueError) as error:
                errors.append(str(error))
                if attempt == 0:
                    time.sleep(0.3)
            finally:
                partial.unlink(missing_ok=True)
    raise ValueError(f"Cannot retrieve verified {name}: {'; '.join(errors)}")


def checksum_rows(field: str) -> dict[str, dict[str, Any]]:
    result = {}
    for line in field.splitlines():
        if not line.strip():
            continue
        checksum, size, name = line.split()
        validate_name(name)
        if name in result or not re.fullmatch("[0-9a-f]{64}", checksum) or not size.isdecimal():
            raise ValueError("Invalid SHA-256 record")
        result[name] = {"name": name, "sha256": checksum, "size": int(size)}
    if not result:
        raise ValueError("Empty SHA-256 table")
    return result


def control_text(raw: bytes) -> str:
    text = raw.decode("utf-8").replace("\r\n", "\n")
    if text.startswith("-----BEGIN PGP SIGNED MESSAGE-----\n"):
        _, sep, rest = text.partition("\n\n")
        payload, marker, _ = rest.partition("\n-----BEGIN PGP SIGNATURE-----\n")
        if not sep or not marker:
            raise ValueError("Malformed clearsigned metadata")
        return re.sub(r"(?m)^- ", "", payload)
    return text


def check_descriptor(raw: bytes, row: dict[str, Any]) -> None:
    message = Parser().parsestr(control_text(raw))
    if (message["Source"], message["Version"]) != (row["package"], row["version"]):
        raise ValueError("Descriptor identity differs from installed source")
    files = {f["name"]: f for f in row["files"] if not f["name"].endswith(".dsc")}
    if checksum_rows(message["Checksums-Sha256"]) != files:
        raise ValueError("Descriptor file set differs from repository index")


def gpgv() -> str:
    binary = shutil.which("gpgv")
    if binary:
        return binary
    git = shutil.which("git")
    if os.name == "nt" and git:
        bundled = Path(git).parents[1] / "usr/bin/gpgv.exe"
        if bundled.is_file():
            return str(bundled)
    raise ValueError("Install gpgv or Git for Windows to verify the signed repository indexes")


def signed_index_spec(release: bytes, key: bytes, suite: str, index_path: str) -> dict[str, Any]:
    # Relative arguments also work with MSYS gpgv on Windows paths containing a colon.
    with tempfile.TemporaryDirectory() as folder:
        (Path(folder) / "archive.gpg").write_bytes(key)
        (Path(folder) / "InRelease").write_bytes(release)
        subprocess.run(
            [gpgv(), "--homedir", ".", "--keyring", "./archive.gpg", "InRelease"],
            cwd=folder,
            stdout=subprocess.DEVNULL,
            check=True,
        )
    fields = Parser().parsestr(control_text(release))
    if fields["Codename"] != suite:
        raise ValueError("Repository codename mismatch")
    matches = [
        line.split() for line in fields["SHA256"].splitlines() if line.split()[-1:] == [index_path]
    ]
    if len(matches) != 1:
        raise ValueError("Missing or duplicate signed index hash")
    checksum, size, _ = matches[0]
    return {"sha256": checksum, "size": int(size)}


def check_index(raw: bytes, index_path: str, rows: list[dict[str, Any]]) -> None:
    expected = {(r["package"], r["version"]): r for r in rows}
    names = {r["package"].encode() for r in rows}
    opener = lzma.decompress if index_path.endswith(".xz") else gzip.decompress
    for paragraph in opener(raw).split(b"\n\n"):
        if paragraph.partition(b"\n")[0].removeprefix(b"Package: ") not in names:
            continue
        fields = Parser().parsestr(paragraph.decode("utf-8"))
        identity = fields["Package"], fields["Version"]
        row = expected.pop(identity, None)
        if row is None:
            continue
        table = checksum_rows(fields["Checksums-Sha256"])
        files = {f["name"]: f for f in row["files"]}
        if (
            fields["Directory"] != row["directory"]
            or files != table
            or len(files) != len(row["files"])
            or sum(n.endswith(".dsc") for n in files) != 1
        ):
            raise ValueError(f"Source row differs from authenticated index: {identity}")
    if expected:
        raise ValueError(f"Source versions absent from index: {sorted(expected)}")


def check_coverage(inventory: bytes, manifest: dict[str, Any]) -> None:
    if digest(inventory) != manifest["inventory_sha256"]:
        raise ValueError("Installed inventory changed")
    installed = {
        (p["source_package"], p["source_version"])
        for image in json.loads(inventory)["images"]
        for p in image["components"]
        if p["ecosystem"] == "deb"
    }
    packages = manifest["packages"]
    if installed != {(r["package"], r["version"]) for r in packages} or len(packages) != len(
        installed
    ):
        raise ValueError("Source coverage differs from installed package versions")
    if {r["index"] for r in packages} != set(manifest["indexes"]):
        raise ValueError("Unbound source index")


def metadata(
    manifest: dict[str, Any], cache: Path, fetch: bool, kit: Path | None = None
) -> dict[str, bytes]:
    result = {"manifest.json": (EVIDENCE / "manifest.json").read_bytes()}
    for name, sha in manifest["keyrings"].items():
        path = safe_path(EVIDENCE / "metadata", name)
        if digest(path.read_bytes()) != sha:
            raise ValueError("Archive keyring changed")
        result["metadata/" + name] = path.read_bytes()
    for label, index in manifest["indexes"].items():
        release_name = f"metadata/{label}.InRelease"
        release = safe_path(EVIDENCE, release_name)
        release_raw = release.read_bytes()
        if digest(release_raw) != index["inrelease_sha256"]:
            raise ValueError("Archived InRelease changed")
        result[release_name] = release_raw
        index_path = index["source_index"]
        spec = signed_index_spec(
            release_raw, result["metadata/" + index["keyring"]], index["suite"], index_path
        )
        name = f"metadata/{label}.{Path(index_path).name}"
        local = safe_path(EVIDENCE, name)
        if local.exists():
            raw = local.read_bytes()
        elif kit is not None:
            with tarfile.open(kit, "r:") as archive:
                member = archive.getmember(name)
                if not member.isfile() or member.size != spec["size"]:
                    raise ValueError("Invalid archived source index")
                stream = archive.extractfile(member)
                assert stream is not None
                raw = stream.read()
        else:
            suite_path = "/dists/" + index["suite"] + "/"
            by_hash = index_path.rsplit("/", 1)[0] + "/by-hash/SHA256/" + spec["sha256"]
            urls = [
                index["mirror"] + suite_path + by_hash,
                index["archive"] + suite_path + index_path,
            ]
            raw = obtain(cache, name, spec, urls, fetch).read_bytes()
        if len(raw) != spec["size"] or digest(raw) != spec["sha256"]:
            raise ValueError("Index differs from signed release")
        check_index(raw, index_path, [r for r in manifest["packages"] if r["index"] == label])
        result[name] = raw
    return result


def pool_files(manifest: dict[str, Any]) -> dict[str, tuple[dict[str, Any], list[str]]]:
    files: dict[str, tuple[dict[str, Any], list[str]]] = {}
    for row in manifest["packages"]:
        repo = manifest["indexes"][row["index"]]
        for f in row["files"]:
            validate_name(f["name"])
            directory = row["directory"]
            if not re.fullmatch(r"pool/(?:[a-z0-9.+~-]+/)*[a-z0-9.+~-]+", directory):
                raise ValueError("Invalid pool directory")
            name = directory + "/" + f["name"]
            urls = [repo["mirror"] + "/" + name]
            if name in manifest["snapshot_file_ids"]:
                locator = manifest["snapshot_file_ids"][name]
                if not re.fullmatch("[a-f0-9]{40}", locator):
                    raise ValueError("Invalid snapshot locator")
                urls.append("https://snapshot.debian.org/file/" + locator)
            urls.append(repo["archive"] + "/" + name)
            if name in files and files[name][0] != f:
                raise ValueError("Conflicting pool file checksums")
            files[name] = f, urls
    return files


def verify_archive(archive_path: Path, expected: dict[str, dict[str, Any]]) -> None:
    seen = set()
    with tarfile.open(archive_path, "r|") as archive:
        for member in archive:
            spec = expected.get(member.name)
            if (
                not member.isfile()
                or spec is None
                or member.name in seen
                or member.size != spec["size"]
            ):
                raise ValueError("Unexpected, repeated or invalid archive member")
            stream = archive.extractfile(member)
            assert stream is not None
            # tarfile's streaming reader does not implement the readinto fast path.
            hasher = hashlib.sha256()
            while chunk := stream.read(BLOCK):
                hasher.update(chunk)
            if hasher.hexdigest() != spec["sha256"]:
                raise ValueError(f"Archive bytes changed: {member.name}")
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError("Incomplete source archive")


def pack(
    destination: Path,
    files: dict[str, Path],
    evidence: dict[str, bytes],
    expected: dict[str, dict[str, Any]],
) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as tmp:
        pending = Path(tmp.name)
    try:
        with tarfile.open(pending, "w", format=tarfile.GNU_FORMAT) as archive:
            for name, data in sorted(evidence.items()):
                header = tarfile.TarInfo(name)
                header.mode, header.size = 0o644, len(data)
                archive.addfile(header, io.BytesIO(data))
            for name, path in sorted(files.items()):
                member = tarfile.TarInfo(name)
                member.mode, member.size = 0o644, path.stat().st_size
                with path.open("rb") as stream:
                    archive.addfile(member, stream)
        verify_archive(pending, expected)
        os.link(pending, destination)  # Publish only a complete archive, never replace a prior one.
    finally:
        pending.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / ".local/debian-sources")
    parser.add_argument("--fetch", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--indexes-only", action="store_true")
    mode.add_argument("--archive", type=Path, help="Write a new, verified source kit")
    mode.add_argument("--verify-archive", type=Path)
    args = parser.parse_args()
    for path in (args.cache, args.archive):
        if path and (path.resolve() == ROOT or not path.resolve().is_relative_to(ROOT)):
            parser.error("Writable paths must be below the repository")
    manifest = json.loads((EVIDENCE / "manifest.json").read_bytes())
    check_coverage(BASE.read_bytes(), manifest)
    evidence = metadata(manifest, args.cache, args.fetch, args.verify_archive)
    pool = pool_files(manifest)
    expected = {name: spec for name, (spec, _) in pool.items()}
    expected.update(
        {name: {"size": len(data), "sha256": digest(data)} for name, data in evidence.items()}
    )
    if args.verify_archive:
        verify_archive(args.verify_archive, expected)
    elif not args.indexes_only:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                n: executor.submit(obtain, args.cache, n, spec, urls, args.fetch)
                for n, (spec, urls) in pool.items()
            }
            paths = {name: future.result() for name, future in futures.items()}
        for row in manifest["packages"]:
            descriptor = next(f["name"] for f in row["files"] if f["name"].endswith(".dsc"))
            check_descriptor(paths[row["directory"] + "/" + descriptor].read_bytes(), row)
        if args.archive:
            pack(args.archive, paths, evidence, expected)
    print(
        f"Verified {len(manifest['packages'])} source versions; {len(pool)} pool files"
        + (" indexed" if args.indexes_only else " checked")
    )


if __name__ == "__main__":
    main()
