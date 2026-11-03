"""Collect installed license evidence from immutable images, without app volumes.

This is a notice inventory, not a source-code offer or a distribution approval.
Exit 0 means collection succeeded, including explicitly listed coverage gaps.
"""

import argparse
import base64
import hashlib
import io
import json
import re
import subprocess
import tarfile
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
NOTICE_NAME = re.compile(
    r"^(licen[cs]e|copying|copyright|notice|patents|unlicense)([._-].*)?$", re.I
)
NOTICE_FIND = (
    "\\( -iname 'license*' -o -iname 'licence*' -o -iname 'copying*' "
    "-o -iname 'notice*' -o -iname 'copyright*' -o -iname 'patents' "
    "-o -iname 'unlicense' -o -path '/usr/share/common-licenses/*' \\)"
)
PYTHON_PROBE = r"""
import base64, importlib.metadata as m, json, pathlib, re, sys
rows = []
for d in sorted(m.distributions(), key=lambda d: d.metadata['Name'].lower()):
    name = d.metadata['Name']
    if name.startswith('marketob-'):
        continue
    files = {}
    for p in d.files or []:
        if (re.match(r'^(licen[cs]e|copying|copyright|notice|patents|unlicense)([._-].*)?$',
                     p.name, re.I) or 'licenses' in p.parts):
            f = pathlib.Path(d.locate_file(p))
            if f.is_file():
                files[str(p)] = base64.b64encode(f.read_bytes()).decode()
    rows.append({'ecosystem': 'pypi', 'name': name, 'version': d.version,
                 'declared_license': (d.metadata.get('License-Expression')
                                      or d.metadata.get('License')),
                 'project_urls': d.metadata.get_all('Project-URL') or [], 'files': files})
p = (pathlib.Path(sys.base_prefix) / 'lib'
     / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'LICENSE.txt')
rows.append({'ecosystem': 'runtime', 'name': 'CPython', 'version': sys.version.split()[0],
             'files': {str(p): base64.b64encode(p.read_bytes()).decode()}})
print(json.dumps(rows))
"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def notice_files(data: bytes) -> dict[str, bytes]:
    """Read regular notice files only, never extract archive paths or links."""
    result = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or "\\" in member.name:
                raise ValueError("Unsafe archive path")
            common = str(path).startswith("usr/share/common-licenses/")
            if not (member.isfile() or member.islnk()) or not (
                common or NOTICE_NAME.fullmatch(path.name)
            ):
                continue
            if member.size > 4_000_000:
                raise ValueError("Unexpected notice size")
            if member.islnk() and (
                ".." in PurePosixPath(member.linkname).parts
                or PurePosixPath(member.linkname).is_absolute()
            ):
                raise ValueError("Unsafe archive link")
            stream = archive.extractfile(member)
            assert stream is not None
            result[str(path)] = stream.read()
    return result


def apk_components(data: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for block in data.strip().split("\n\n"):
        # Only package headers, not the later file inventory with repeated keys.
        fields = dict(line.split(":", 1) for line in block.split("\nF:", 1)[0].splitlines())
        result.append(
            {
                "ecosystem": "apk",
                "name": fields["P"],
                "version": fields["V"],
                "declared_license": fields.get("L"),
                "source_package": fields.get("o"),
                "source_commit": fields.get("c"),
                "homepage": fields.get("U"),
                "notices": [],
            }
        )
    return result


def go_modules(data: str) -> tuple[str, list[dict[str, Any]]]:
    rows = []
    for line in data.splitlines()[1:]:
        fields = line.strip().split("\t")
        if fields[0] == "=>":
            raise ValueError("Go replacements need explicit source mapping")
        if fields[0] == "dep":
            rows.append(
                {
                    "ecosystem": "go",
                    "name": fields[1],
                    "version": fields[2],
                    "module_sum": fields[3],
                    "notices": [],
                }
            )
    if not rows:
        raise ValueError("Go build module inventory missing")
    return data.splitlines()[0].split()[-1], rows


def go_cache_path(name: str, version: str) -> str:
    escaped = "".join("!" + c.lower() if c.isupper() else c for c in name)
    return f"go/pkg/mod/{escaped}@{version}/"


def pinned_source_notices(source: dict[str, Any], directory: Path) -> dict[str, bytes]:
    """A separately downloaded sdist is evidence only after the lock digest matches."""
    filename = PurePosixPath(urlsplit(source["url"]).path).name
    data = (directory / filename).read_bytes()
    if "sha256:" + digest(data) != source["hash"]:
        raise ValueError("Source archive does not match uv.lock")
    return notice_files(data)


class Collector:
    def __init__(self, wsl: str | None) -> None:
        self.prefix = ["wsl", "-d", wsl, "--exec"] if wsl else []
        self.texts: dict[str, bytes] = {}

    def docker(self, *args: str, stdin: bytes | None = None) -> bytes:
        result = subprocess.run(
            self.prefix + ["docker", *args],
            input=stdin,
            capture_output=True,
            timeout=180,
            check=True,
        )
        return result.stdout

    def identity(self, image: str) -> dict[str, str]:
        obj = json.loads(self.docker("image", "inspect", image))[0]
        # Deliberately omit environment, labels, local paths and container state.
        return {
            "reference": image,
            "id": obj["Id"],
            "os": obj["Os"],
            "architecture": obj["Architecture"],
        }

    def run(self, image: str, entrypoint: str, *args: str, stdin: bytes | None = None) -> bytes:
        return self.docker(
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--entrypoint",
            entrypoint,
            image,
            *args,
            stdin=stdin,
        )

    def record(self, path: str, data: bytes) -> dict[str, str]:
        if not data.strip():
            raise ValueError("Empty notice")
        sha = digest(data)
        self.texts[sha] = data
        return {"source_path": path, "file": f"texts/{sha}.txt", "sha256": sha}

    def system(self, image: str, alpine: bool) -> tuple[list[dict[str, Any]], list[Any]]:
        if alpine:
            rows = apk_components(self.run(image, "cat", "/lib/apk/db/installed").decode())
        else:
            fmt = "${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\n"
            raw = self.run(image, "dpkg-query", "-W", "-f=" + fmt).decode()
            rows = [
                dict(
                    zip(
                        ("name", "version", "source_package", "source_version"),
                        line.split("\t"),
                        strict=True,
                    )
                )
                for line in raw.splitlines()
            ]
            for row in rows:
                row.update(ecosystem="deb", notices=[])
        archive = self.run(
            image,
            "sh",
            "-c",
            "set --; for p in /usr/share/doc /usr/share/common-licenses "
            "/usr/local/share/licenses /usr/share/licenses; do "
            'if [ -d "$p" ]; then set -- "$@" "$p"; fi; done; '
            'if [ "$#" -gt 0 ]; then paths=$(find -L "$@" -type f '
            + NOTICE_FIND
            + ') || exit 1; if [ -n "$paths" ]; then '
            + 'printf "%s\\n" "$paths" | tar -chf - -T -; fi; fi',
        )
        files = notice_files(archive) if archive else {}
        common = [
            self.record(p, b)
            for p, b in sorted(files.items())
            if p.startswith("usr/share/common-licenses/")
        ]
        for row in rows:
            name = row["name"].split(":")[0]
            prefixes = (f"usr/share/doc/{name}/", f"usr/share/licenses/{name}/")
            row["notices"] = [
                self.record(p, b) for p, b in sorted(files.items()) if p.startswith(prefixes)
            ]
        # Include the manually installed helper, outside dpkg ownership.
        extra = [
            self.record(p, b)
            for p, b in sorted(files.items())
            if p.startswith("usr/local/share/licenses/")
        ]
        return rows, common + extra

    def python(self, image: str, source_dir: Path | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = json.loads(
            self.run(image, "python", "-", stdin=PYTHON_PROBE.encode())
        )
        for row in rows:
            row["notices"] = [
                self.record(p, base64.b64decode(b)) for p, b in sorted(row.pop("files").items())
            ]
            if not row["notices"] and source_dir:
                lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
                normalized = re.sub(r"[-_.]+", "-", row["name"]).lower()
                package = next(
                    p
                    for p in lock["package"]
                    if p["name"] == normalized and p["version"] == row["version"]
                )
                source = package["sdist"]
                row["source_archive"] = {"url": source["url"], "hash": source["hash"]}
                row["notices"] = [
                    self.record(p, b)
                    for p, b in sorted(pinned_source_notices(source, source_dir).items())
                ]
        return rows

    def go(self, image: str, builder: str, binary: str) -> dict[str, Any]:
        identity = self.identity(builder)
        built = "/out/" + PurePosixPath(binary).name
        runtime_sha = self.run(image, "sha256sum", binary).decode().split()[0]
        build_sha = self.run(identity["id"], "sha256sum", built).decode().split()[0]
        if runtime_sha != build_sha:
            raise ValueError("Builder binary does not match the delivered binary")
        version, rows = go_modules(self.run(identity["id"], "go", "version", "-m", built).decode())
        # Verify cached module content against go.sum before using its notices.
        self.run(identity["id"], "sh", "-c", "cd /src && go mod verify")
        sums = set(self.run(identity["id"], "cat", "/src/go.sum").decode().splitlines())
        for row in rows:
            if f"{row['name']} {row['version']} {row['module_sum']}" not in sums:
                raise ValueError("Binary module checksum absent from builder go.sum")
        archive = self.run(
            identity["id"],
            "sh",
            "-c",
            "paths=$(find /go/pkg/mod /usr/local/go /src -type f "
            + NOTICE_FIND
            + ') || exit 1; printf "%s\\n" "$paths" | tar -chf - -T -',
        )
        files = notice_files(archive)
        for row in rows:
            prefix = go_cache_path(row["name"], row["version"])
            row["notices"] = [
                self.record(p, b) for p, b in sorted(files.items()) if p.startswith(prefix)
            ]
        rows.append(
            {
                "ecosystem": "runtime",
                "name": "Go",
                "version": version,
                "notices": [
                    self.record(p, b)
                    for p, b in sorted(files.items())
                    if p.startswith("usr/local/go/")
                ],
            }
        )
        if binary.endswith("/gosu"):
            rows.append(
                {
                    "ecosystem": "go",
                    "name": "github.com/tianon/gosu",
                    "version": "1.19",
                    "notices": [
                        self.record(p, b) for p, b in sorted(files.items()) if p.startswith("src/")
                    ],
                }
            )
        return {
            "builder": identity,
            "binary_path": binary,
            "binary_sha256": runtime_sha,
            "components": rows,
        }


def write_bundle(output: Path, report: dict[str, Any], texts: dict[str, bytes]) -> None:
    # Content-addressed flat members prevent host-path leaks and path traversal.
    with (output / "texts.tar.gz").open("wb") as dest:
        import gzip

        with gzip.GzipFile(fileobj=dest, filename="", mode="wb", mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as archive:
                for sha, data in sorted(texts.items()):
                    member = tarfile.TarInfo(f"texts/{sha}.txt")
                    member.size, member.mode = len(data), 0o644
                    archive.addfile(member, io.BytesIO(data))
    report["texts_archive_sha256"] = digest((output / "texts.tar.gz").read_bytes())
    report["unique_notice_texts"] = len(texts)
    (output / "inventory.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


def verify_bundle(output: Path) -> None:
    report = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
    raw = (output / "texts.tar.gz").read_bytes()
    if digest(raw) != report["texts_archive_sha256"]:
        raise ValueError("Archive digest mismatch")
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        contents = {}
        for member in archive:
            if not member.isfile() or not re.fullmatch(r"texts/[0-9a-f]{64}\.txt", member.name):
                raise ValueError("Unexpected bundle member")
            stream = archive.extractfile(member)
            assert stream is not None
            data = stream.read()
            if digest(data) != Path(member.name).stem or member.name in contents:
                raise ValueError("Notice digest mismatch or duplicate")
            contents[member.name] = data
    used = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if "source_path" in value:
                if (
                    value["file"] not in contents
                    or digest(contents[value["file"]]) != value["sha256"]
                ):
                    raise ValueError("Broken notice reference")
                used.add(value["file"])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(report)
    if used != set(contents) or len(contents) != report["unique_notice_texts"]:
        raise ValueError("Unreferenced notice or wrong count")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--wsl")
    parser.add_argument("--release", default="68958f1")
    parser.add_argument("--proxy-builder")
    parser.add_argument("--db-builder")
    parser.add_argument(
        "--python-sdist-dir",
        type=Path,
        help="Offline source archives, verified against uv.lock, for missing notices",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output == ROOT:
        parser.error("Output must be below this repository")
    if args.verify:
        verify_bundle(output)
        print("Notice archive hashes and references verified")
        return 0
    output.mkdir(parents=True, exist_ok=False)
    collector = Collector(args.wsl)
    report: dict[str, Any] = {
        "schema_version": 1,
        "release": args.release,
        "images": [],
        "repository_project_license": tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )["project"].get("license", "not_selected"),
        "corresponding_source_bundle": "not_prepared",
        "limitations": [
            "Installed runtime dependencies only; dev/build-only tools excluded",
            "Notice filename discovery is not a full source/header license review",
            "Bundled native or Rust code needs separate attribution review",
            "Collected texts do not certify redistribution compliance",
        ],
        "gaps": [],
    }
    try:
        for role in ("api", "bot", "db", "proxy"):
            identity = collector.identity(f"marketob-{role}:{args.release}")
            rows, common = collector.system(identity["id"], role == "proxy")
            if role in ("api", "bot"):
                rows += collector.python(identity["id"], args.python_sdist_dir)
            target: dict[str, Any] = {
                "role": role,
                **identity,
                "components": rows,
                "shared_notices": common,
            }
            builder = (
                args.proxy_builder if role == "proxy" else args.db_builder if role == "db" else None
            )
            if builder:
                binary = "/usr/bin/caddy" if role == "proxy" else "/usr/local/bin/gosu"
                go = collector.go(identity["id"], builder, binary)
                rows += go.pop("components")
                target["go_source_evidence"] = go
            elif role in ("proxy", "db"):
                report["gaps"].append({"role": role, "reason": "go_builder_not_supplied"})
            for row in rows:
                if not row["notices"]:
                    report["gaps"].append(
                        {
                            "role": role,
                            "ecosystem": row["ecosystem"],
                            "name": row["name"],
                            "version": row["version"],
                            "reason": "notice_not_found",
                        }
                    )
            report["images"].append(target)
        write_bundle(output, report, collector.texts)
        verify_bundle(output)
    except OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError:
        (output / "INCOMPLETE.txt").write_text(
            "Collection failed. Do not distribute this bundle.\n"
        )
        raise
    print(
        json.dumps(
            {
                "images": len(report["images"]),
                "notice_texts": len(collector.texts),
                "coverage_gaps": len(report["gaps"]),
                "compliance_verdict": "not_assessed",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
