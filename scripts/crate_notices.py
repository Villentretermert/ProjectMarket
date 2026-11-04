"""Verify the crate notice supplement against its release and optional source inputs."""

import argparse
import io
import json
import re
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.alpine_notices import read_source, safe_path, selected_notice, write_sources
from scripts.collect_notices import ROOT, digest, verify_bundle
from scripts.embedded_notices import tar_member

BASE = ROOT / "third_party/68958f1-native"
SUPPLEMENT = ROOT / "third_party/68958f1-crate-notices"


def remote_source(crate: dict[str, Any], commit: str, path: str) -> tuple[str, str]:
    repo = crate["repository"].removeprefix("https://github.com/")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid immutable GitHub source")
    safe_path(ROOT, path)
    return (
        f"supplement/{repo}/{commit}/{path}",
        f"https://raw.githubusercontent.com/{repo}/{commit}/{path}",
    )


def check_commit(
    raw: bytes,
    crate: dict[str, Any],
    row: dict[str, Any],
    cache: Path,
    fetch: bool,
    sources: dict[str, bytes],
) -> None:
    prefix = f"{row['name']}-{row['version']}/"
    if "source_matches" not in row:
        vcs = json.loads(tar_member(raw, prefix + ".cargo_vcs_info.json"))
        if vcs["git"]["sha1"] != row["commit"] or vcs["git"].get("dirty"):
            raise ValueError("Source commit differs from published crate")
        return
    # Older archives lack VCS metadata. Bind the original manifest and every Rust file.
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        required = {m.name for m in archive if m.isfile() and m.name.endswith(".rs")}
    required.add(prefix + "Cargo.toml.orig")
    matches = row["source_matches"]
    if {m["member"] for m in matches} != required or len(matches) != len(required):
        raise ValueError("Incomplete source tree comparison")
    manifest_path = next(m["path"] for m in matches if m["member"] == prefix + "Cargo.toml.orig")
    upstream_dir = PurePosixPath(manifest_path).parent
    for match in matches:
        relative = match["member"].removeprefix(prefix).removesuffix(".orig")
        if match["path"] != (upstream_dir / relative).as_posix():
            raise ValueError("Source tree member mapped to a different path")
        data = tar_member(raw, match["member"])
        name, url = remote_source(crate, row["commit"], match["path"])
        spec = dict(path=name, url=url, sha256=digest(data), git_blob=match["git_blob"])
        sources[name] = read_source(cache, spec, fetch)


def verify(
    base: Path,
    supplement: Path,
    cache: Path | None = None,
    fetch: bool = False,
    source_archive: Path | None = None,
) -> None:
    verify_bundle(base)
    verify_bundle(supplement)
    manifest = json.loads((supplement / "inventory.json").read_bytes())
    base_raw = (base / "inventory.json").read_bytes()
    if digest(base_raw) != manifest["base_inventory_sha256"]:
        raise ValueError("Base release inventory changed")
    evidence = json.loads(base_raw)["embedded_source_evidence"]
    gaps = {(c["name"], c["version"]) for c in evidence["notice_gaps"]}
    crates = {(c["name"], c["version"]): c for c in evidence["inputs"] if c["kind"] == "crate"}
    rows = manifest["crates"]
    if {(r["name"], r["version"]) for r in rows} != gaps or len(rows) != len(gaps):
        raise ValueError("Supplement must account for each prior crate gap once")
    sources: dict[str, bytes] = {}
    for row in rows:
        crate = crates[row["name"], row["version"]]
        if row["crate_sha256"] != crate["sha256"] or not row["notices"]:
            raise ValueError("Unbound crate or missing notices")
        raw = None
        if cache is not None:
            raw = read_source(cache, crate, fetch)
            sources[crate["path"]] = raw
            if "commit" in row:
                check_commit(raw, crate, row, cache, fetch, sources)
        for notice in row["notices"]:
            if "member" in notice:
                prefix = f"{row['name']}-{row['version']}/"
                if not notice["member"].startswith(prefix):
                    raise ValueError("Notice outside selected crate")
                safe_path(ROOT, notice["member"])
                expected = crate["path"] + "!/" + notice["member"]
                if raw is not None:
                    selected_notice(raw, notice)
            else:
                name, url = remote_source(crate, row["commit"], notice["path"])
                expected = url
                if cache is not None:
                    spec = dict(
                        path=name, url=url, sha256=notice["sha256"], git_blob=notice["git_blob"]
                    )
                    sources[name] = read_source(cache, spec, fetch)
            if (
                notice["source_path"] != expected
                or notice["file"] != f"texts/{notice['sha256']}.txt"
            ):
                raise ValueError("Incorrect notice source reference")
    if source_archive is not None:
        if cache is None:
            raise ValueError("Source archive requires full verification")
        # Pair the supplement with every pinned prior source, including sdists and notices.
        for source in evidence["inputs"]:
            if source["kind"] != "wheel" and source["path"] not in sources:
                sources[source["path"]] = read_source(cache, source, fetch)
        write_sources(source_archive, sources)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, help="Recheck crate and upstream bytes in this cache")
    parser.add_argument("--fetch", action="store_true", help="Fetch missing verified inputs")
    parser.add_argument(
        "--source-archive", type=Path, help="Create a new archive of checked inputs"
    )
    args = parser.parse_args()
    if (args.fetch or args.source_archive) and args.cache is None:
        parser.error("--fetch and --source-archive require --cache")
    for path in (args.cache, args.source_archive):
        if path is not None and (path.resolve() == ROOT or not path.resolve().is_relative_to(ROOT)):
            parser.error("Writable paths must be below the repository")
    verify(BASE, SUPPLEMENT, args.cache, args.fetch, args.source_archive)
    print("Crate notices verified" + (" against source bytes" if args.cache else " offline"))


if __name__ == "__main__":
    main()
