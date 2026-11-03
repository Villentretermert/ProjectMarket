"""Supplement a pinned notice snapshot from verified Alpine source inputs.

APKBUILD is read as data, never sourced. Fetching is optional and does not run
package tools. The source-input archive is not a complete build environment.
"""

import argparse
import base64
import copy
import gzip
import hashlib
import io
import json
import re
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.collect_notices import ROOT, Collector, digest, verify_bundle, write_bundle


def safe_path(root: Path, name: str) -> Path:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError("Unsafe source path")
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()) or target == root.resolve():
        raise ValueError("Source path escapes cache")
    return target


def verify_file(raw: bytes, spec: dict[str, Any]) -> None:
    if digest(raw) != spec["sha256"]:
        raise ValueError("Source SHA-256 mismatch")
    if "sha512" in spec and hashlib.sha512(raw).hexdigest() != spec["sha512"]:
        raise ValueError("APKBUILD source SHA-512 mismatch")
    if "git_blob" in spec:
        blob = b"blob " + str(len(raw)).encode() + b"\0" + raw
        if hashlib.sha1(blob).hexdigest() != spec["git_blob"]:
            raise ValueError("Git blob mismatch")


def read_source(cache: Path, spec: dict[str, Any], fetch: bool) -> bytes:
    path = safe_path(cache, spec["path"])
    if not path.exists() and fetch:
        errors = []
        for url in dict.fromkeys([spec["url"], spec.get("upstream_url", spec["url"])]):
            if not url.startswith("https://"):
                raise ValueError("Only HTTPS source URLs are accepted")
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "MarkeTOB-notices/1"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read(100_000_001)
                if len(raw) > 100_000_000:
                    raise ValueError("Oversized source input")
                if spec.get("encoding") == "github_blob":
                    blob = json.loads(raw)
                    if blob["encoding"] != "base64":
                        raise ValueError("Unexpected GitHub blob encoding")
                    raw = base64.b64decode(blob["content"])
                verify_file(raw, spec)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                break
            except (OSError, ValueError) as error:
                errors.append(type(error).__name__)
        else:
            raise ValueError("No verified source download: " + spec["path"] + " " + str(errors))
    raw = path.read_bytes()
    verify_file(raw, spec)
    return raw


def selected_notice(raw: bytes, selection: dict[str, Any]) -> bytes:
    if "member" in selection:
        # No extraction and no following archive links, including for source headers.
        name = selection["member"]
        safe_path(Path.cwd(), name)
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            matches = [m for m in archive if m.name == name]
            if len(matches) != 1 or not matches[0].isfile() or matches[0].size > 4_000_000:
                raise ValueError("Ambiguous or non-regular notice member")
            stream = archive.extractfile(matches[0])
            assert stream is not None
            raw = stream.read()
    start, end = selection.get("start", 0), selection.get("end", len(raw))
    if not 0 <= start < end <= len(raw):
        raise ValueError("Invalid notice byte range")
    selected = raw[start:end]
    if digest(selected) != selection["sha256"]:
        raise ValueError("Selected notice digest mismatch")
    return selected


def verify_recipe(origin: dict[str, Any], files: dict[str, bytes]) -> None:
    recipe = files[origin["recipe_path"]].decode("utf-8")
    version = re.search(r"^pkgver=([\w.]+)$", recipe, re.M)
    revision = re.search(r"^pkgrel=(\d+)$", recipe, re.M)
    name = re.search(r"^pkgname=([\w-]+)$", recipe, re.M)
    if (
        not version
        or not revision
        or not name
        or name[1] != origin["name"]
        or version[1] + "-r" + revision[1] != origin["version"]
    ):
        raise ValueError("Recipe identity mismatch")
    checksums = dict(
        (name, sha) for sha, name in re.findall(r"^([0-9a-f]{128})  (.+)$", recipe, re.M)
    )
    listed = {f["name"]: f["sha512"] for f in origin["checksum_inputs"]}
    if checksums != listed or len(listed) != len(origin["checksum_inputs"]):
        raise ValueError("Recipe source coverage mismatch")
    for item in origin["checksum_inputs"]:
        folder = "sources" if item["kind"] == "upstream" else "aports"
        raw = files[f"{folder}/{origin['name']}/{item['name']}"]
        if hashlib.sha512(raw).hexdigest() != item["sha512"]:
            raise ValueError("Recipe input checksum mismatch")


def write_sources(destination: Path, files: dict[str, bytes]) -> None:
    with (
        destination.open("xb") as stream,
        gzip.GzipFile(fileobj=stream, filename="", mode="wb", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for name, raw in sorted(files.items()):
            safe_path(destination.parent, name)
            member = tarfile.TarInfo(name)
            member.mode, member.size = 0o644, len(raw)
            archive.addfile(member, io.BytesIO(raw))


def verify_supplement(base: Path, manifest: dict[str, Any], output: Path) -> None:
    """Offline CI check of source/notice associations as well as text integrity."""
    verify_bundle(base)
    verify_bundle(output)
    raw = (base / "inventory.json").read_bytes()
    if digest(raw) != manifest["base_inventory_sha256"]:
        raise ValueError("Base inventory changed")
    before = json.loads(raw)
    after = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
    if len(before["images"]) != len(after["images"]):
        raise ValueError("Image coverage changed")
    for original, updated in zip(before["images"], after["images"], strict=True):
        if original["role"] != "proxy":
            if original != updated:
                raise ValueError("Non-Alpine inventory changed")
            continue
        if original["id"] != manifest["proxy_image_id"] or updated["id"] != original["id"]:
            raise ValueError("Proxy image changed")
        if {k: v for k, v in original.items() if k != "components"} != {
            k: v for k, v in updated.items() if k != "components"
        }:
            raise ValueError("Proxy provenance changed")
        origins = {o["name"]: o for o in manifest["origins"]}
        expected_origins = {
            p["source_package"] for p in original["components"] if p["ecosystem"] == "apk"
        }
        if set(origins) != expected_origins or len(origins) != len(manifest["origins"]):
            raise ValueError("Source origin coverage changed")
        if len(original["components"]) != len(updated["components"]):
            raise ValueError("Component coverage changed")
        for old, new in zip(original["components"], updated["components"], strict=True):
            if old["ecosystem"] != "apk":
                if old != new:
                    raise ValueError("Non-Alpine component changed")
                continue
            origin = origins[old["source_package"]]
            if (origin["commit"], origin["version"]) != (old["source_commit"], old["version"]):
                raise ValueError("Origin identity mismatch")
            for key in old.keys() - {"notices"}:
                if old[key] != new.get(key):
                    raise ValueError("Installed package identity changed")
            expected = []
            for selection in origin["notices"]:
                path = selection["input"]
                if "member" in selection:
                    path += "!/" + selection["member"]
                expected.append((path, selection["sha256"], selection["kind"]))
            actual = [(n["source_path"], n["sha256"], n["kind"]) for n in new["notices"]]
            if actual != expected:
                raise ValueError("Source notice association changed")
            for selection, notice in zip(origin["notices"], new["notices"], strict=True):
                expected_range = (
                    [selection["start"], selection["end"]] if "start" in selection else None
                )
                if notice.get("byte_range") != expected_range:
                    raise ValueError("Source notice byte range changed")
    expected_gaps = [
        g
        for g in before["gaps"]
        if not (
            g.get("ecosystem") == "apk"
            and any(
                p["name"] == g["name"] and p["notices"]
                for t in after["images"]
                for p in t["components"]
            )
        )
    ]
    if after["gaps"] != expected_gaps:
        raise ValueError("Unresolved gap lost")


def supplement(
    base: Path,
    manifest: dict[str, Any],
    cache: Path,
    output: Path,
    fetch: bool = False,
    source_archive: Path | None = None,
) -> None:
    verify_bundle(base)
    raw_inventory = (base / "inventory.json").read_bytes()
    if digest(raw_inventory) != manifest["base_inventory_sha256"]:
        raise ValueError("Base inventory changed")
    report = copy.deepcopy(json.loads(raw_inventory))
    proxy = next(t for t in report["images"] if t["role"] == "proxy")
    if proxy["id"] != manifest["proxy_image_id"]:
        raise ValueError("Proxy image changed")
    collector = Collector(None)
    with tarfile.open(base / "texts.tar.gz") as archive:
        for member in archive:
            stream = archive.extractfile(member)
            assert stream is not None
            collector.texts[PurePosixPath(member.name).stem] = stream.read()
    packages = [p for p in proxy["components"] if p["ecosystem"] == "apk"]
    expected = {(p["source_package"], p["version"], p["source_commit"]) for p in packages}
    actual = {(o["name"], o["version"], o["commit"]) for o in manifest["origins"]}
    if expected != actual or len(actual) != len(manifest["origins"]):
        raise ValueError("Alpine package/source coverage mismatch")
    all_files: dict[str, bytes] = {}
    proof = []
    for origin in manifest["origins"]:
        files = {f["path"]: read_source(cache, f, fetch) for f in origin["files"]}
        if len(files) != len(origin["files"]) or set(files) & set(all_files):
            raise ValueError("Duplicate source input")
        verify_recipe(origin, files)
        all_files.update(files)
        notices = []
        for selection in origin["notices"]:
            raw = selected_notice(files[selection["input"]], selection)
            path = selection["input"] + (
                "!/" + selection["member"] if "member" in selection else ""
            )
            notice: dict[str, Any] = dict(collector.record(path, raw))
            notice["kind"] = selection["kind"]
            if "start" in selection:
                notice["byte_range"] = [selection["start"], selection["end"]]
            notices.append(notice)
        for package in packages:
            if package["source_package"] == origin["name"]:
                package["notices"] = notices
                package["notice_origin"] = "verified_source_inputs"
                package["notice_review"] = origin["review_notes"]
        proof.append(
            {
                "name": origin["name"],
                "version": origin["version"],
                "commit": origin["commit"],
                "files_verified": len(files),
                "checksum_inputs_verified": len(origin["checksum_inputs"]),
                "notice_selections": len(notices),
                "review_notes": origin["review_notes"],
            }
        )
    standard_notices = []
    for spec in manifest["standard_terms"]:
        raw = read_source(cache, spec, fetch)
        all_files[spec["path"]] = raw
        standard_notices.append({**collector.record(spec["path"], raw), "note": spec["note"]})
    # Common GPL/MPL texts already in the base bundle remain shared, not new attribution.
    report["alpine_source_evidence"] = {
        "origins": proof,
        "standard_terms": standard_notices,
        "complete_license_verdict": "not_assessed",
    }
    report["gaps"] = [
        g
        for g in report["gaps"]
        if not (
            g.get("ecosystem") == "apk"
            and any(p["name"] == g["name"] and p["notices"] for p in packages)
        )
    ]
    if source_archive:
        write_sources(source_archive, all_files)
        report["alpine_source_evidence"]["source_input_archive"] = {
            "sha256": digest(source_archive.read_bytes()),
            "files": len(all_files),
            "bytes": source_archive.stat().st_size,
            "scope": "Verified recipes/inputs only; build environment and rebuild not verified",
        }
    write_bundle(output, report, collector.texts)
    verify_bundle(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=ROOT / "third_party/68958f1")
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "third_party/alpine-68958f1/sources.json"
    )
    parser.add_argument("--cache", type=Path, default=ROOT / ".local/alpine-sources")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--source-archive", type=Path)
    args = parser.parse_args()
    for path in [args.cache, args.output] + ([args.source_archive] if args.source_archive else []):
        if not path.resolve().is_relative_to(ROOT) or path.resolve() == ROOT:
            parser.error("Writable paths must be below this repository")
    if args.verify:
        verify_supplement(
            args.base, json.loads(args.manifest.read_text(encoding="utf-8")), args.output
        )
        print("Source notice associations and bundle hashes verified")
        return 0
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        supplement(
            args.base,
            json.loads(args.manifest.read_text(encoding="utf-8")),
            args.cache,
            args.output,
            args.fetch,
            args.source_archive,
        )
    except OSError, ValueError, KeyError, tarfile.TarError:
        (args.output / "INCOMPLETE.txt").write_text("Incomplete source notice collection.\n")
        raise
    report = json.loads((args.output / "inventory.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "texts": report["unique_notice_texts"],
                "remaining_gaps": len(report["gaps"]),
                "source_origins": len(report["alpine_source_evidence"]["origins"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
