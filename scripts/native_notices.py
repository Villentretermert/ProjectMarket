"""Verify wheel SBOMs and compiler evidence; collect supplemental native notices.

SBOMs describe producer-declared all-target dependencies, not a binary link map.
Offline verification replays saved evidence; collection also checks wheel bytes.
No downloaded code, compiler or build script is executed.
"""

import argparse
import io
import json
import re
import struct
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

from scripts.alpine_notices import read_source, safe_path, selected_notice, verify_file
from scripts.collect_notices import ROOT, digest, verify_bundle, write_bundle
from scripts.embedded_notices import REGISTRY, notice_reference, verify_wheel


def elf_evidence(raw: bytes) -> dict[str, Any]:
    """Read only ELF64 little-endian section metadata and defined dynsym names."""
    if len(raw) < 64 or raw[:7] != b"\x7fELF\x02\x01\x01":
        raise ValueError("Expected ELF64 little-endian version 1")

    def region(offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(raw):
            raise ValueError("ELF section outside file")
        return raw[offset : offset + size]

    def cstring(data: bytes, offset: int) -> str:
        end = data.find(b"\0", offset)
        if offset < 0 or offset >= len(data) or end < 0:
            raise ValueError("Invalid ELF string offset")
        return data[offset:end].decode("utf-8", errors="replace")

    offset = struct.unpack_from("<Q", raw, 40)[0]
    size, count, names_index = struct.unpack_from("<HHH", raw, 58)
    if size != 64 or not 0 < names_index < count:
        raise ValueError("Unsupported ELF section table")
    table = region(offset, count * size)
    sections = list(struct.iter_unpack("<IIQQQQIIQQ", table))
    names = sections[names_index]
    if names[1] != 3:
        raise ValueError("Expected section string table")
    strings = region(names[4], names[5])
    comments: list[str] = []
    seen_comment = False
    markers = set()
    for section in sections:
        name = cstring(strings, section[0])
        if name == ".comment":
            if seen_comment or section[1] != 1:
                raise ValueError("Duplicate or invalid ELF comment section")
            seen_comment = True
            comments = [s.decode("utf-8") for s in region(section[4], section[5]).split(b"\0") if s]
        if section[1] != 11:
            continue
        if section[9] != 24 or section[5] % 24 or section[6] >= count:
            raise ValueError("Invalid ELF dynamic symbol table")
        names = sections[section[6]]
        if names[1] != 3:
            raise ValueError("Invalid ELF dynamic string table")
        dynamic_strings = region(names[4], names[5])
        for symbol in struct.iter_unpack("<IBBHQQ", region(section[4], section[5])):
            symbol_name = cstring(dynamic_strings, symbol[0])
            # An undefined import does not prove the statically linked implementation.
            if (
                symbol_name == "cffistatic_ffi_call"
                and 0 < symbol[3] < count
                and symbol[1] & 15 == 2
                and symbol[5] > 0
            ):
                markers.add(symbol_name)
    return {
        "comments": comments,
        "rustc_commits": sorted({s.decode() for s in re.findall(rb"/rustc/([0-9a-f]{40})/", raw)}),
        "defined_markers": sorted(markers),
    }


def summarize_sbom(
    bom: dict[str, Any], parent: dict[str, Any], inputs: list[dict[str, Any]]
) -> dict[str, Any]:
    if bom["bomFormat"] != "CycloneDX" or bom["specVersion"] != "1.5":
        raise ValueError("Unsupported SBOM format")
    root = bom["metadata"]["component"]
    root_name = "jsonschema-py" if parent["name"] == "jsonschema-rs" else parent["name"]
    if (root["name"], root["version"]) != (root_name, parent["version"]):
        raise ValueError("SBOM root differs from wheel package")
    properties = bom["metadata"].get("properties", [])
    if properties != [{"name": "cdx:rustc:sbom:target:all_targets", "value": "true"}]:
        raise ValueError("Expected explicit all-target SBOM scope")
    crates = {(s["name"], s["version"]): s for s in inputs if s["kind"] == "crate"}
    workspace = {(e["name"], e["version"]): e for e in parent["workspace_entries"]}
    nodes: dict[str, str] = {}
    rows = []
    for component in [root, *bom["components"]]:
        ref = component["bom-ref"]
        key = component["name"], component["version"]
        identity = "@".join(key)
        if ref in nodes or identity in nodes.values():
            raise ValueError("Duplicate SBOM component")
        nodes[ref] = identity
        if ref.startswith(REGISTRY + "#"):
            spec = crates.get(key)
            hashes = component.get("hashes", [])
            if (
                spec is None
                or parent["name"] not in spec["parents"]
                or hashes != [{"alg": "SHA-256", "content": spec["sha256"]}]
            ):
                raise ValueError("SBOM crate differs from pinned source")
            rows.append({"id": identity, "kind": "registry", "sha256": spec["sha256"]})
        elif ref.startswith("path+file://") and key in workspace and workspace[key]["member"]:
            rows.append({"id": identity, "kind": "workspace"})
        else:
            raise ValueError("Unbound SBOM component")
    edges = {}
    for dependency in bom["dependencies"]:
        ref, targets = dependency["ref"], dependency.get("dependsOn", [])
        if ref not in nodes or ref in edges or len(set(targets)) != len(targets):
            raise ValueError("Duplicate or unknown SBOM dependency node")
        if any(target not in nodes for target in targets):
            raise ValueError("Dangling SBOM dependency")
        edges[ref] = targets
    if set(edges) != set(nodes):
        raise ValueError("Incomplete SBOM dependency coverage")
    reached, pending = set(), [root["bom-ref"]]
    while pending:
        ref = pending.pop()
        if ref not in reached:
            reached.add(ref)
            pending.extend(edges[ref])
    if reached != set(nodes):
        raise ValueError("Unreachable SBOM component")
    return {
        "root": nodes[root["bom-ref"]],
        "scope": "producer SBOM, all targets; not exact linked Linux code",
        "components": sorted(rows, key=lambda row: row["id"]),
        "dependencies": {nodes[k]: sorted(nodes[t] for t in v) for k, v in edges.items()},
    }


def evidence_files(directory: Path, manifest: dict[str, Any]) -> dict[str, bytes]:
    raw = (directory / "evidence.tar.gz").read_bytes()
    if digest(raw) != manifest["evidence_archive_sha256"]:
        raise ValueError("Evidence archive changed")
    expected = {s["path"]: s for s in manifest["evidence"]}
    if len(expected) != len(manifest["evidence"]):
        raise ValueError("Duplicate evidence specification")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            safe_path(directory, member.name)
            if (
                member.name not in expected
                or member.name in files
                or not member.isfile()
                or member.size > 4_000_000
            ):
                raise ValueError("Unexpected, duplicate or oversized evidence")
            stream = archive.extractfile(member)
            assert stream is not None
            data = stream.read()
            verify_file(data, expected[member.name])
            files[member.name] = data
    if set(files) != set(expected):
        raise ValueError("Missing evidence file")
    return files


def proof(
    manifest: dict[str, Any], embedded: dict[str, Any], files: dict[str, bytes]
) -> dict[str, Any]:
    parents = {p["name"]: p for p in embedded["parents"]}
    wheels = {w["name"]: w for w in manifest["wheels"]}
    if set(wheels) != {p["name"] for p in parents.values() if "wheel" in p}:
        raise ValueError("Wheel evidence coverage changed")
    if len(wheels) != len(manifest["wheels"]):
        raise ValueError("Duplicate wheel evidence")
    summaries = {}
    for name, wheel in wheels.items():
        parent = parents[name]
        if [f["file"] for f in wheel["native"]] != parent["installed_native_files"]:
            raise ValueError("Native file association changed")
        if "cargo_lock" in parent:
            summaries[name] = summarize_sbom(
                json.loads(files[wheel["sbom"]["path"]]), parent, embedded["inputs"]
            )
    covered = []
    notice_specs = []
    for chain in manifest["toolchains"]:
        channel = tomllib.loads(files[chain["channel"]].decode())
        package = channel["pkg"]["rustc"]
        distribution = package["target"]["x86_64-unknown-linux-gnu"]
        source = chain["distribution"]
        if (
            package["version"] != chain["compiler"]
            or distribution["xz_url"] != source["url"]
            or distribution["xz_hash"] != source["sha256"]
        ):
            raise ValueError("Rust distribution differs from channel manifest")
        for parent_name in chain["parents"]:
            for native in wheels[parent_name]["native"]:
                elf = native["elf"]
                if (
                    "rustc version " + chain["compiler"] not in elf["comments"]
                    or elf["rustc_commits"] != [chain["commit"]]
                    or not chain["compiler"].split("(")[1].startswith(chain["commit"][:9])
                ):
                    raise ValueError("Rust compiler evidence mismatch")
            covered.append(parent_name)
        notice_specs.append(source)
    if sorted(covered) != sorted(summaries):
        raise ValueError("Rust toolchain coverage differs from SBOM coverage")
    ffi = manifest["libffi"]
    verify_file(files[ffi["license"]["path"]], ffi["license"])
    for notice in ffi["license"]["notices"]:
        selected_notice(files[ffi["license"]["path"]], notice)
    recipe = files[ffi["recipe"]].decode()
    if not all(
        token in recipe
        for token in (
            "https://github.com/libffi/libffi/archive/v" + ffi["version"] + ".tar.gz",
            "--enable-shared=no",
            "-Dffi_call=cffistatic_ffi_call",
        )
    ) or not any(
        "cffistatic_ffi_call" in n["elf"]["defined_markers"] for n in wheels["cffi"]["native"]
    ):
        raise ValueError("libffi recipe/static symbol evidence mismatch")
    notice_specs.append(ffi["license"])
    return {
        "scope": manifest["scope"],
        "wheels": manifest["wheels"],
        "sboms": summaries,
        "toolchains": manifest["toolchains"],
        "libffi": ffi,
        "notices": [notice_reference(s, n) for s in notice_specs for n in s["notices"]],
        "open_items": manifest["open_items"],
    }


def distribution_notices(raw: bytes, selections: list[dict[str, Any]]) -> dict[str, bytes]:
    """Decompress each compiler archive once, retaining only bounded notice members."""
    expected = {n["member"]: n for n in selections}
    if len(expected) != len(selections):
        raise ValueError("Duplicate notice selection")
    seen = set()
    texts = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r|*") as archive:
        for member in archive:
            if member.name not in expected:
                continue
            safe_path(ROOT, member.name)
            if member.name in seen or not member.isfile() or member.size > 4_000_000:
                raise ValueError("Duplicate, linked or oversized distribution notice")
            seen.add(member.name)
            stream = archive.extractfile(member)
            assert stream is not None
            selection = {k: v for k, v in expected[member.name].items() if k != "member"}
            texts[selection["sha256"]] = selected_notice(stream.read(), selection)
    if seen != set(expected):
        raise ValueError("Missing distribution notice")
    return texts


def run(
    directory: Path,
    base: Path,
    embedded_path: Path,
    output: Path,
    cache: Path | None = None,
    wheel_cache: Path | None = None,
    fetch: bool = False,
) -> None:
    manifest = json.loads((directory / "sources.json").read_text(encoding="utf-8"))
    raw_base, raw_embedded = (base / "inventory.json").read_bytes(), embedded_path.read_bytes()
    if (
        digest(raw_base) != manifest["base_inventory_sha256"]
        or digest(raw_embedded) != manifest["embedded_manifest_sha256"]
    ):
        raise ValueError("Pinned base evidence changed")
    verify_bundle(base)
    embedded = json.loads(raw_embedded)
    files = evidence_files(directory, manifest)
    result = proof(manifest, embedded, files)
    before = json.loads(raw_base)
    if cache is not None:
        if wheel_cache is None:
            raise ValueError("Collection requires wheel cache")
        for wheel in manifest["wheels"]:
            parent = next(p for p in embedded["parents"] if p["name"] == wheel["name"])
            spec = next(s for s in embedded["inputs"] if s["path"] == parent["wheel"])
            raw = read_source(wheel_cache, spec, fetch)
            verify_wheel(raw, parent["installed_native_files"])
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for native in wheel["native"]:
                    if elf_evidence(archive.read(native["file"]["path"])) != native["elf"]:
                        raise ValueError("ELF evidence differs from wheel")
                if "sbom" in wheel:
                    sbom = wheel["sbom"]
                    members = [m for m in archive.infolist() if m.filename == sbom["member"]]
                    if len(members) != 1 or members[0].file_size > 4_000_000:
                        raise ValueError("Missing, duplicate or oversized wheel SBOM")
                    if archive.read(members[0]) != files[sbom["path"]]:
                        raise ValueError("SBOM differs from wheel")
        texts = {}
        with tarfile.open(base / "texts.tar.gz") as archive:
            for member in archive:
                stream = archive.extractfile(member)
                assert stream is not None
                texts[Path(member.name).stem] = stream.read()
        for chain in manifest["toolchains"]:
            spec = chain["distribution"]
            raw = read_source(cache, spec, fetch)
            texts.update(distribution_notices(raw, spec["notices"]))
        spec = manifest["libffi"]["license"]
        for notice in spec["notices"]:
            texts[notice["sha256"]] = selected_notice(files[spec["path"]], notice)
        before["native_build_evidence"] = result
        write_bundle(output, before, texts)
    if (output / "INCOMPLETE.txt").exists():
        raise ValueError("Incomplete native notice collection")
    verify_bundle(output)
    after = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
    if after.pop("native_build_evidence") != result:
        raise ValueError("Native evidence associations changed")
    before.pop("native_build_evidence", None)
    for report in (before, after):
        report.pop("texts_archive_sha256")
        report.pop("unique_notice_texts")
    if before != after:
        raise ValueError("Prior inventory or gaps changed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=ROOT / "third_party/native-68958f1")
    parser.add_argument("--base", type=Path, default=ROOT / "third_party/68958f1-embedded")
    parser.add_argument(
        "--embedded", type=Path, default=ROOT / "third_party/embedded-68958f1/sources.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=ROOT / ".local/native-notice-inputs")
    parser.add_argument("--wheel-cache", type=Path, default=ROOT / ".local/embedded-sources")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    for path in (args.output, args.cache, args.wheel_cache):
        if not path.resolve().is_relative_to(ROOT) or path.resolve() == ROOT:
            parser.error("Writable paths must be below the repository")
    if not args.verify:
        args.output.mkdir(parents=True, exist_ok=False)
    try:
        run(
            args.evidence,
            args.base,
            args.embedded,
            args.output,
            None if args.verify else args.cache,
            args.wheel_cache,
            args.fetch,
        )
    except OSError, ValueError, KeyError, tarfile.TarError, zipfile.BadZipFile:
        if not args.verify:
            (args.output / "INCOMPLETE.txt").write_text("Incomplete native notice collection.\n")
        raise
    print("Native notice associations and saved SBOM evidence verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
