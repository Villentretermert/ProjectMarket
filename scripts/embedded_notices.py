"""Collect notices from pinned Python sdists, wheel files and Cargo lock inputs.

Cargo locks include development and other-platform inputs. This source inventory
does not assert that every listed crate is linked into the installed binaries.
Downloaded code and package build scripts are never executed.
"""

import argparse
import io
import json
import re
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

from scripts.alpine_notices import read_source, safe_path, selected_notice, write_sources
from scripts.collect_notices import ROOT, Collector, digest, verify_bundle, write_bundle

SCOPE = "Source/lock inputs; exact linked Rust graph and complete source delivery not verified"
REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def tar_member(raw: bytes, name: str) -> bytes:
    safe_path(ROOT, name)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        matches = [m for m in archive if m.name == name]
        if len(matches) != 1 or not matches[0].isfile() or matches[0].size > 4_000_000:
            raise ValueError("Missing, duplicate, linked or oversized evidence member")
        stream = archive.extractfile(matches[0])
        assert stream is not None
        return stream.read()


def locked_crates(
    locks: dict[str, bytes],
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for parent, raw in sorted(locks.items()):
        for package in tomllib.loads(raw.decode())["package"]:
            if "source" not in package:
                continue  # Workspace entries are checked separately, including absent sources.
            if package["source"] != REGISTRY:
                raise ValueError("Non-registry Cargo input requires explicit handling")
            key = package["name"], package["version"]
            if key in result and result[key]["sha256"] != package["checksum"]:
                raise ValueError("Conflicting Cargo checksums")
            row = result.setdefault(key, {"sha256": package["checksum"], "parents": []})
            if parent in row["parents"]:
                raise ValueError("Duplicate Cargo input")
            row["parents"].append(parent)
    return result


def validate_manifest(
    manifest: dict[str, Any], evidence_dir: Path, base: Path, uv_lock: Path
) -> dict[str, bytes]:
    raw = (base / "inventory.json").read_bytes()
    if digest(raw) != manifest["base_inventory_sha256"]:
        raise ValueError("Base inventory changed")
    before = json.loads(raw)
    images = {i["role"]: i for i in before["images"]}
    inputs = {s["path"]: s for s in manifest["inputs"]}
    parents = {p["name"]: p for p in manifest["parents"]}
    if len(inputs) != len(manifest["inputs"]) or len(parents) != len(manifest["parents"]):
        raise ValueError("Duplicate input or parent")
    packages = {p["name"]: p for p in tomllib.loads(uv_lock.read_text(encoding="utf-8"))["package"]}
    locks = {}
    referenced = set()
    for parent in parents.values():
        locked = packages[parent["name"]]
        if parent["version"] != locked["version"]:
            raise ValueError("Python version differs from uv.lock")
        for kind in ("sdist", "wheel"):
            if kind not in parent:
                continue
            spec = inputs[parent[kind]]
            candidates = [locked["sdist"]] if kind == "sdist" else locked["wheels"]
            if not any(
                c["url"] == spec["url"] and c["hash"] == "sha256:" + spec["sha256"]
                for c in candidates
            ) or (spec["kind"], spec["name"], spec["version"]) != (
                kind,
                parent["name"],
                parent["version"],
            ):
                raise ValueError("Python source/wheel not pinned in uv.lock")
            referenced.add(spec["path"])
        for role, image_id in parent["images"].items():
            image = images[role]
            if image["id"] != image_id or not any(
                c["ecosystem"] == "pypi"
                and normalized(c["name"]) == parent["name"]
                and c["version"] == parent["version"]
                for c in image["components"]
            ):
                raise ValueError("Installed image/package identity changed")
        if not parent["images"]:
            raise ValueError("Missing installed package association")
        if "cargo_lock" in parent:
            spec = parent["cargo_lock"]
            raw = safe_path(evidence_dir, spec["file"]).read_bytes()
            if digest(raw) != spec["sha256"]:
                raise ValueError("Cargo lock evidence changed")
            locks[parent["name"]] = raw
            local = {
                (p["name"], p["version"])
                for p in tomllib.loads(raw.decode())["package"]
                if "source" not in p
            }
            entries = parent.get("workspace_entries", [])
            if local != {(e["name"], e["version"]) for e in entries} or len(local) != len(entries):
                raise ValueError("Workspace entry coverage differs from Cargo lock")
    expected = locked_crates(locks)
    actual = {}
    for spec in inputs.values():
        safe_path(ROOT, spec["path"])
        if spec["kind"] == "crate":
            key = spec["name"], spec["version"]
            if key in actual:
                raise ValueError("Duplicate crate identity")
            actual[key] = {"sha256": spec["sha256"], "parents": spec["parents"]}
            referenced.add(spec["path"])
        elif spec["kind"] == "upstream_notice":
            if not spec["crates"] or not spec.get("git_blob"):
                raise ValueError("Unbound upstream notice")
            for name, version in spec["crates"]:
                crate = next(
                    s
                    for s in inputs.values()
                    if s["kind"] == "crate" and (s["name"], s["version"]) == (name, version)
                )
                if (
                    crate["vcs"]["git"]["sha1"] != spec["commit"]
                    or crate["repository"].removesuffix(".git") != spec["repository"]
                ):
                    raise ValueError("Upstream notice does not match crate VCS")
            referenced.add(spec["path"])
    if actual != expected or referenced != set(inputs):
        raise ValueError("Cargo/input coverage differs from pinned locks")
    return locks


def verify_wheel(raw: bytes, files: list[dict[str, Any]]) -> None:
    expected = {f["path"]: (f["sha256"], f["bytes"]) for f in files}
    if not expected or len(expected) != len(files):
        raise ValueError("Missing or duplicate installed native files")
    actual = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in archive.infolist():
            safe_path(ROOT, member.filename)
            if member.is_dir() or ".so" not in Path(member.filename).name:
                continue
            if (
                member.filename in actual
                or member.file_size > 100_000_000
                or ((member.external_attr >> 16) & 0o170000) == 0o120000
            ):
                raise ValueError("Duplicate, linked or oversized native wheel member")
            data = archive.read(member)
            actual[member.filename] = digest(data), len(data)
    if actual != expected:
        raise ValueError("Wheel native files differ from installed image")


def notice_reference(spec: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    path = spec["path"] + ("!/" + selection["member"] if "member" in selection else "")
    result: dict[str, Any] = {
        "source_path": path,
        "file": f"texts/{selection['sha256']}.txt",
        "sha256": selection["sha256"],
        "kind": selection["kind"],
    }
    if "start" in selection:
        result["byte_range"] = [selection["start"], selection["end"]]
    return result


def source_evidence(manifest: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for spec in manifest["inputs"]:
        row = {k: v for k, v in spec.items() if k != "notices"}
        row["notices"] = [notice_reference(spec, n) for n in spec["notices"]]
        rows.append(row)
    supplemental = {
        tuple(c)
        for spec in manifest["inputs"]
        if spec["kind"] == "upstream_notice"
        for c in spec["crates"]
        if spec["notices"]
    }
    gaps = [
        {
            "name": s["name"],
            "version": s["version"],
            "reason": "notice_not_found_in_crate",
            "scope": "lock input; Linux linkage not established",
        }
        for s in manifest["inputs"]
        if s["kind"] == "crate"
        and not s["notices"]
        and (s["name"], s["version"]) not in supplemental
    ]
    return {
        "scope": SCOPE,
        "parents": manifest["parents"],
        "inputs": rows,
        "workspace_gaps": [
            {
                "parent": p["name"],
                "name": e["name"],
                "version": e["version"],
                "reason": "workspace_manifest_absent_from_sdist",
            }
            for p in manifest["parents"]
            for e in p.get("workspace_entries", [])
            if e["member"] is None
        ],
        "notice_gaps": gaps,
        "open_items": manifest["open_items"],
    }


def verify_supplement(
    base: Path,
    manifest: dict[str, Any],
    evidence_dir: Path,
    output: Path,
    uv_lock: Path = ROOT / "uv.lock",
) -> None:
    if (output / "INCOMPLETE.txt").exists():
        raise ValueError("Incomplete collection")
    validate_manifest(manifest, evidence_dir, base, uv_lock)
    verify_bundle(base)
    verify_bundle(output)
    before = json.loads((base / "inventory.json").read_text(encoding="utf-8"))
    after = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
    proof = after.pop("embedded_source_evidence")
    if proof != source_evidence(manifest):
        raise ValueError("Source notice associations changed")
    for report in (before, after):
        report.pop("texts_archive_sha256")
        report.pop("unique_notice_texts")
    if before != after:
        raise ValueError("Installed inventory or prior gaps changed")


def collect(
    base: Path,
    manifest: dict[str, Any],
    evidence_dir: Path,
    cache: Path,
    output: Path,
    fetch: bool = False,
    source_archive: Path | None = None,
    uv_lock: Path = ROOT / "uv.lock",
) -> None:
    locks = validate_manifest(manifest, evidence_dir, base, uv_lock)
    verify_bundle(base)
    report = json.loads((base / "inventory.json").read_text(encoding="utf-8"))
    collector = Collector(None)
    with tarfile.open(base / "texts.tar.gz") as archive:
        for member in archive:
            stream = archive.extractfile(member)
            assert stream is not None
            collector.texts[Path(member.name).stem] = stream.read()
    parents = {p["name"]: p for p in manifest["parents"]}
    sources = {}
    for spec in manifest["inputs"]:
        raw = read_source(cache, spec, fetch)
        if spec["kind"] == "crate":
            prefix = f"{spec['name']}-{spec['version']}/"
            package = tomllib.loads(tar_member(raw, prefix + "Cargo.toml").decode())["package"]
            if (package["name"], package["version"], package.get("license")) != (
                spec["name"],
                spec["version"],
                spec["declared_license"],
            ):
                raise ValueError("Crate metadata differs from manifest")
            if package.get("repository") != spec.get("repository"):
                raise ValueError("Crate repository differs from manifest")
            if (
                "vcs" in spec
                and json.loads(tar_member(raw, prefix + ".cargo_vcs_info.json")) != spec["vcs"]
            ):
                raise ValueError("Crate VCS evidence changed")
        elif spec["kind"] == "sdist":
            parent = parents[spec["name"]]
            if "cargo_lock" in parent:
                actual = tar_member(raw, parent["cargo_lock"]["member"])
                if actual != locks[parent["name"]]:
                    raise ValueError("Cargo lock differs from pinned sdist")
                for entry in parent.get("workspace_entries", []):
                    if entry["member"] is None:
                        continue
                    raw_manifest = tar_member(raw, entry["member"])
                    package = tomllib.loads(raw_manifest.decode())["package"]
                    if digest(raw_manifest) != entry["sha256"] or (
                        package["name"],
                        package["version"],
                    ) != (entry["name"], entry["version"]):
                        raise ValueError("Workspace manifest differs from source")
        elif spec["kind"] == "wheel":
            verify_wheel(raw, parents[spec["name"]]["installed_native_files"])
        for selection in spec["notices"]:
            data = selected_notice(raw, selection)
            ref = notice_reference(spec, selection)
            collector.record(ref["source_path"], data)
        if spec["kind"] != "wheel":
            sources[spec["path"]] = raw
    if source_archive:
        write_sources(source_archive, sources)
    report["embedded_source_evidence"] = source_evidence(manifest)
    write_bundle(output, report, collector.texts)
    verify_supplement(base, manifest, evidence_dir, output, uv_lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=ROOT / "third_party/68958f1-alpine")
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "third_party/embedded-68958f1/sources.json"
    )
    parser.add_argument("--cache", type=Path, default=ROOT / ".local/embedded-sources")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    for path in [args.cache, args.output] + ([args.source_archive] if args.source_archive else []):
        if not path.resolve().is_relative_to(ROOT) or path.resolve() == ROOT:
            parser.error("Writable paths must be below the repository")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.verify:
        verify_supplement(args.base, manifest, args.manifest.parent, args.output)
        print("Embedded source associations, retained gaps and notice hashes verified")
        return 0
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        collect(
            args.base,
            manifest,
            args.manifest.parent,
            args.cache,
            args.output,
            args.fetch,
            args.source_archive,
        )
    except OSError, ValueError, KeyError, StopIteration, tarfile.TarError, zipfile.BadZipFile:
        (args.output / "INCOMPLETE.txt").write_text("Incomplete source notice collection.\n")
        raise
    report = json.loads((args.output / "inventory.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "texts": report["unique_notice_texts"],
                "source_inputs": len(manifest["inputs"]),
                "crate_notice_gaps": len(report["embedded_source_evidence"]["notice_gaps"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
