"""Collect recorded Go inputs and verify their bytes/content offline (stdlib only).

The h1 algorithm follows go.dev/ref/mod#go-sum-files. No source is extracted or
executed. Hashes bind recorded inputs; they are not a reproducible-build claim.
"""

import argparse
import base64
import hashlib
import json
import re
import shutil
import stat
import subprocess
import tarfile
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "third_party/go-schema-20261109"
INVENTORY = "third_party/schema-20261109/inventory.json"
RECIPE = "third_party/delivery-schema-20261109/recipe.json"
GAPS = [
    "toolchain-bootstrap-and-full-rebuild",
    "native-build-graph",
    "remaining-source-and-attribution-gaps",
    "release-acceptance",
]
LIMIT = 500_000_000


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_spec(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        return {
            "sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
            "size": path.stat().st_size,
        }


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode()


def object_json(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    result = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(result, dict):
        raise ValueError("Expected JSON object")
    return result


def safe_path(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or ".." in path.parts
        or str(path) != name
        or any(c in name for c in "\\:\n\r\x00")
        or name == "."
    ):
        raise ValueError("Unsafe source path")


def flat_name(name: str) -> None:
    safe_path(name)
    if "/" in name:
        raise ValueError("Expected flat filename")


def escaped(name: str) -> str:
    return "".join("!" + c.lower() if "A" <= c <= "Z" else c for c in name)


def sums(raw: bytes) -> dict[tuple[str, str, str], str]:
    rows = {}
    for line in raw.decode().splitlines():
        name, version, checksum = line.split()
        safe_path(name)
        kind = "mod" if version.endswith("/go.mod") else "zip"
        version = version.removesuffix("/go.mod")
        if not re.fullmatch(r"v[0-9A-Za-z.+-]+", version):
            raise ValueError("Invalid module version")
        if not re.fullmatch(r"h1:[A-Za-z0-9+/]{43}=", checksum):
            raise ValueError("Invalid module checksum")
        key = (name, version, kind)
        if key in rows:
            raise ValueError("Duplicate go.sum entry")
        rows[key] = checksum
    return rows


def h1(entries: dict[str, str]) -> str:
    summary = "".join(f"{entries[n]}  {n}\n" for n in sorted(entries)).encode()
    return "h1:" + base64.b64encode(hashlib.sha256(summary).digest()).decode()


def module_hash(path: Path, row: dict[str, Any]) -> str:
    if row["kind"] == "mod":
        return h1({"go.mod": digest(path.read_bytes())})
    prefix = row["name"] + "@" + row["version"] + "/"
    hashes: dict[str, str] = {}
    expanded = 0
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            name = member.filename
            safe_path(name)
            if (
                not name.startswith(prefix)
                or name in hashes
                or member.is_dir()
                or member.flag_bits & 1
                or stat.S_ISLNK(member.external_attr >> 16)
            ):
                raise ValueError("Invalid module ZIP member")
            expanded += member.file_size
            if expanded > LIMIT or len(hashes) >= 100_000:
                raise ValueError("Module ZIP limit exceeded")
            with archive.open(member) as stream:
                checksum = hashlib.sha256()
                while chunk := stream.read(1024 * 1024):
                    checksum.update(chunk)
                hashes[name] = checksum.hexdigest()
    if not hashes:
        raise ValueError("Empty module ZIP")
    return h1(hashes)


def check_spec(path: Path, spec: dict[str, Any]) -> None:
    if (
        path.is_symlink()
        or not path.is_file()
        or file_spec(path) != {k: spec[k] for k in ("sha256", "size")}
    ):
        raise ValueError("Source size/SHA-256 mismatch: " + path.name)


def validate_plan(plan: dict[str, Any], directory: Path) -> None:
    if (
        plan["schema"] != "marketob-go-source/v1"
        or plan["coverage_state"] != "partial"
        or plan["open_items"] != GAPS
        or not re.fullmatch(r"[0-9a-f]{40}", plan["release_commit"])
    ):
        raise ValueError("Invalid plan or coverage claim")
    expected_evidence = {
        "inventory.json",
        "runtime.json",
        "go-release.json",
        "go-VERSION",
        "go-LICENSE",
        "go-PATENTS",
        "proxy-main.go",
        "Dockerfile.db",
        "Dockerfile.proxy",
    }
    expected_evidence |= {
        f"{r}-{n}"
        for r in ("db", "proxy")
        for n in ("go.mod", "go.sum", "build-info.txt", "go-env.json", "go-verify.txt")
    }
    expected_evidence |= {"db-" + n for n in ("main.go", "version.go", "setup-user.go", "LICENSE")}
    if set(plan["evidence"]) != expected_evidence:
        raise ValueError("Incomplete observed evidence")
    for name, spec in plan["evidence"].items():
        check_spec(directory / name, spec)
    inventory = object_json((directory / "inventory.json").read_bytes())
    images = {i["role"]: i for i in inventory["images"]}
    runtime = object_json((directory / "runtime.json").read_bytes())
    if set(runtime) != {"db", "proxy"}:
        raise ValueError("Missing Go image role")
    expected: dict[tuple[str, str, str], dict[str, Any]] = {}
    for role, record in runtime.items():
        image = images[role]
        evidence = image["go_source_evidence"]
        if record != {
            "image_id": image["id"],
            "builder_id": evidence["builder"]["id"],
            "binary_path": evidence["binary_path"],
            "binary_sha256": evidence["binary_sha256"],
        }:
            raise ValueError("Runtime/builder identity mismatch")
        version = next(c["version"] for c in image["components"] if c["name"] == "Go")
        env = object_json((directory / f"{role}-go-env.json").read_bytes())
        if env != {
            "CGO_ENABLED": "0",
            "GOARCH": "amd64",
            "GOOS": "linux",
            "GOTOOLCHAIN": "local",
            "GOVERSION": version,
        }:
            raise ValueError("Go environment mismatch")
        info = (directory / f"{role}-build-info.txt").read_text().splitlines()
        if info[0].split()[-1] != version or any(line.strip().startswith("=>") for line in info):
            raise ValueError("Unmapped Go replacement or toolchain")
        deps = [tuple(line.split()[1:]) for line in info if line.strip().startswith("dep\t")]
        installed = {
            (c["name"], c["version"], c["module_sum"])
            for c in image["components"]
            if "module_sum" in c
        }
        if set(deps) != installed or len(deps) != len(installed):
            raise ValueError("Build metadata differs from installed modules")
        locked = sums((directory / f"{role}-go.sum").read_bytes())
        for name, ver, checksum in installed:
            if locked.get((name, ver, "zip")) != checksum:
                raise ValueError("Installed module absent from go.sum")
        for key, checksum in locked.items():
            if key in expected and expected[key]["h1"] != checksum:
                raise ValueError("Conflicting role sums")
            expected.setdefault(key, {"h1": checksum, "roles": []})["roles"].append(role)
        if (directory / f"{role}-go-verify.txt").read_text().strip() != "all modules verified":
            raise ValueError("Builder go mod verify missing")
        if (directory / "go-VERSION").read_text().splitlines()[0] != version:
            raise ValueError("Go source version mismatch")
        notices = {
            n["source_path"]: n["sha256"]
            for c in image["components"]
            if c["name"] == "Go"
            for n in c["notices"]
        }
        for name in ("LICENSE", "PATENTS"):
            if digest((directory / ("go-" + name)).read_bytes()) != notices["usr/local/go/" + name]:
                raise ValueError("Go notice differs from installed inventory")
    found = {}
    for row in plan["modules"]:
        key = (row["name"], row["version"], row["kind"])
        if key in found:
            raise ValueError("Duplicate planned module")
        found[key] = {"h1": row["h1"], "roles": row["roles"]}
        location = escaped(row["name"]) + "/@v/" + escaped(row["version"]) + "." + row["kind"]
        if (
            row["url"] != "https://proxy.golang.org/" + location
            or row["filename"] != row["sha256"] + "." + row["kind"]
        ):
            raise ValueError("Module source location mismatch")
    if found != expected:
        raise ValueError("Source coverage differs from complete go.sum union")
    release = object_json((directory / "go-release.json").read_bytes())
    sources = {s["kind"]: s for s in plan["sources"]}
    if len(plan["sources"]) != 2 or set(sources) != {"toolchain", "gosu"}:
        raise ValueError("Missing root source")
    source = sources["toolchain"]
    if (
        any(source[k] != release[k] for k in ("filename", "version", "sha256", "size"))
        or source["version"] != (directory / "go-VERSION").read_text().splitlines()[0]
        or source["filename"] != source["version"] + ".src.tar.gz"
        or source["url"] != "https://go.dev/dl/" + source["filename"]
        or release["kind"] != "source"
    ):
        raise ValueError("Official Go source mismatch")
    gosu = sources["gosu"]
    dockerfile = (directory / "Dockerfile.db").read_text()
    if (
        gosu["version"] != "1.19"
        or gosu["filename"] != "gosu-1.19.tar.gz"
        or gosu["url"] != "https://codeload.github.com/tianon/gosu/tar.gz/refs/tags/1.19"
        or f"ADD --checksum=sha256:{gosu['sha256']} {gosu['url']} " not in dockerfile
    ):
        raise ValueError("gosu source differs from pinned recipe")
    for row in plan["modules"] + plan["sources"]:
        flat_name(row["filename"])
        if (
            not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
            or type(row["size"]) is not int
            or not 0 < row["size"] <= LIMIT
        ):
            raise ValueError("Invalid input size/hash")


def verify_tar(path: Path, root: str, wanted: dict[str, bytes]) -> None:
    seen: set[str] = set()
    found: set[str] = set()
    expanded = 0
    with tarfile.open(path, "r|gz") as archive:
        for member in archive:
            name = member.name.rstrip("/") if member.isdir() else member.name
            safe_path(name)
            if (
                not (name == root or name.startswith(root + "/"))
                or name in seen
                or not (member.isfile() or member.isdir() or member.issym() or member.islnk())
                or len(seen) >= 100_000
            ):
                raise ValueError("Invalid root source member")
            seen.add(name)
            # Upstream gosu .dockerignore is a symlink. Preserve it as opaque
            # archive data; no links are followed and observed files must be regular.
            expanded += member.size
            if expanded > LIMIT:
                raise ValueError("Root source limit exceeded")
            if name in wanted:
                if not member.isfile() or member.size != len(wanted[name]):
                    raise ValueError("Source observation size/type mismatch")
                stream = archive.extractfile(member)
                assert stream is not None
                if stream.read() != wanted[name]:
                    raise ValueError("Root source observation differs")
                found.add(name)
    if found != set(wanted):
        raise ValueError("Missing root source observations")


def verify_inputs(plan: dict[str, Any], directory: Path) -> None:
    for row in plan["modules"] + plan["sources"]:
        check_spec(directory / row["filename"], row)
    for row in plan["modules"]:
        path = directory / row["filename"]
        if module_hash(path, row) != row["h1"]:
            raise ValueError("Go h1 content mismatch")
        if row["name"] == "github.com/caddyserver/caddy/v2" and row["kind"] == "zip":
            with zipfile.ZipFile(path) as archive:
                main = archive.read(row["name"] + "@" + row["version"] + "/cmd/caddy/main.go")
            if main != (directory / "proxy-main.go").read_bytes():
                raise ValueError("Caddy wrapper differs from verified source")
    for source in plan["sources"]:
        if source["kind"] == "toolchain":
            wanted = {
                "go/" + n: (directory / ("go-" + n)).read_bytes()
                for n in ("VERSION", "LICENSE", "PATENTS")
            }
            root = "go"
        else:
            root = "gosu-" + source["version"]
            wanted = {
                root + "/" + n: (directory / ("db-" + n)).read_bytes()
                for n in ("go.mod", "go.sum", "main.go", "version.go", "setup-user.go", "LICENSE")
            }
        verify_tar(directory / source["filename"], root, wanted)


def verify(directory: Path, expected_sha: str) -> dict[str, Any]:
    if (
        not re.fullmatch(r"[0-9a-f]{64}", expected_sha)
        or file_spec(directory / "manifest.json")["sha256"] != expected_sha
    ):
        raise ValueError("Manifest SHA-256 mismatch")
    manifest = object_json((directory / "manifest.json").read_bytes())
    if manifest["schema"] != "marketob-go-kit/v1":
        raise ValueError("Invalid kit schema")
    for name, spec in manifest["files"].items():
        flat_name(name)
        check_spec(directory / name, spec)
    if {p.name for p in directory.iterdir()} != set(manifest["files"]) | {"manifest.json"}:
        raise ValueError("Missing or unexpected kit files")
    plan = object_json((directory / "source-plan.json").read_bytes())
    required = set(plan["evidence"]) | {"source-plan.json", "verify.py", "README.md"}
    required |= {r["filename"] for r in plan["modules"] + plan["sources"]}
    if set(manifest["files"]) != required:
        raise ValueError("Incomplete kit coverage")
    validate_plan(plan, directory)
    verify_inputs(plan, directory)
    return {
        "manifest_sha256": expected_sha,
        "module_inputs": len(plan["modules"]),
        "root_sources": len(plan["sources"]),
        "files": len(required) + 1,
        "bytes": sum(p.stat().st_size for p in directory.iterdir()),
        "coverage_state": "partial",
        "open_items": GAPS,
    }


def check_repository() -> dict[str, Any]:
    plan = object_json((EVIDENCE / "source-plan.json").read_bytes())
    recipe = object_json((ROOT / RECIPE).read_bytes())
    if (
        plan["release_commit"] != recipe["release_commit"]
        or plan["evidence"]["inventory.json"]["sha256"] != recipe["bound_files"][INVENTORY]
        or file_spec(ROOT / INVENTORY) != plan["evidence"]["inventory.json"]
    ):
        raise ValueError("Plan differs from delivered release")
    validate_plan(plan, EVIDENCE)
    return plan


def collect(output: Path, inputs: Path | None, fetch: bool) -> dict[str, Any]:
    plan = check_repository()
    output.mkdir(parents=True, exist_ok=False)
    try:
        for name in [*plan["evidence"], "source-plan.json", "README.md"]:
            shutil.copyfile(EVIDENCE / name, output / name)
        (output / "verify.py").write_bytes(Path(__file__).read_bytes().replace(b"\r\n", b"\n"))

        def obtain(row: dict[str, Any]) -> None:
            target = output / row["filename"]
            if inputs:
                shutil.copyfile(inputs / row["filename"], target)
            elif fetch:
                with urllib.request.urlopen(row["url"], timeout=90) as response:
                    if not response.url.startswith("https://"):
                        raise ValueError("Insecure download redirect")
                    raw = response.read(row["size"] + 1)
                target.write_bytes(raw)
            else:
                raise ValueError("Pass --inputs or --fetch")
            check_spec(target, row)

        rows = {r["filename"]: r for r in plan["modules"] + plan["sources"]}
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(obtain, rows.values()))
        manifest = {
            "schema": "marketob-go-kit/v1",
            "files": {p.name: file_spec(p) for p in sorted(output.iterdir(), key=lambda p: p.name)},
        }
        (output / "manifest.json").write_bytes(json_bytes(manifest))
        return verify(output, file_spec(output / "manifest.json")["sha256"])
    except Exception:
        (output / "INCOMPLETE.txt").write_text("Incomplete source kit; do not distribute.\n")
        raise


def probe(output: Path, wsl: str | None) -> dict[str, Any]:
    """Repeat only public build observations in disposable, offline containers."""
    plan = check_repository()
    inventory = object_json((EVIDENCE / "inventory.json").read_bytes())
    prefix = ["wsl", "-d", wsl, "--exec", "docker"] if wsl else ["docker"]
    output.mkdir(parents=True, exist_ok=False)

    def run(image: str, *command: str) -> bytes:
        return subprocess.check_output(
            prefix
            + [
                "run",
                "--rm",
                "--pull",
                "never",
                "--network",
                "none",
                "--read-only",
                "--entrypoint",
                command[0],
                image,
                *command[1:],
            ],
            timeout=120,
        )

    records = {}
    for image in inventory["images"]:
        role = image["role"]
        if role not in ("db", "proxy"):
            continue
        evidence = image["go_source_evidence"]
        builder = evidence["builder"]["id"]
        binary = evidence["binary_path"]
        built = "/out/" + PurePosixPath(binary).name
        for identity, path in ((image["id"], binary), (builder, built)):
            if run(identity, "sha256sum", path).decode().split()[0] != evidence["binary_sha256"]:
                raise ValueError("Observed binary differs from delivered image")
        commands = {
            "build-info.txt": ("go", "version", "-m", built),
            "go-env.json": (
                "go",
                "env",
                "-json",
                "GOVERSION",
                "GOOS",
                "GOARCH",
                "CGO_ENABLED",
                "GOTOOLCHAIN",
            ),
            "go-verify.txt": ("sh", "-c", "cd /src && GOPROXY=off GOSUMDB=off go mod verify"),
            **{name: ("cat", "/src/" + name) for name in ("go.mod", "go.sum", "main.go")},
        }
        if role == "db":
            commands.update(
                {n: ("cat", "/src/" + n) for n in ("version.go", "setup-user.go", "LICENSE")}
            )
        for name, command in commands.items():
            (output / f"{role}-{name}").write_bytes(run(builder, *command))
        for name in ("VERSION", "LICENSE", "PATENTS"):
            raw = run(builder, "cat", "/usr/local/go/" + name)
            target = output / ("go-" + name)
            if target.exists() and target.read_bytes() != raw:
                raise ValueError("Builder toolchain observations differ")
            target.write_bytes(raw)
        records[role] = {
            "image_id": image["id"],
            "builder_id": builder,
            "binary_path": binary,
            "binary_sha256": evidence["binary_sha256"],
        }
    (output / "runtime.json").write_bytes(json_bytes(records))
    for path in output.iterdir():
        check_spec(path, plan["evidence"][path.name])
    return {"observed_roles": sorted(records), "files_matched": len(list(output.iterdir()))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-plan", action="store_true")
    mode.add_argument("--collect", type=Path)
    mode.add_argument("--verify", type=Path)
    mode.add_argument("--probe", type=Path)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--sha256")
    parser.add_argument("--wsl")
    args = parser.parse_args()
    if args.verify:
        if not args.sha256:
            parser.error("--verify requires independently supplied manifest --sha256")
        result = verify(args.verify, args.sha256)
    elif args.collect or args.probe:
        output = args.collect or args.probe
        if (
            not output.resolve().is_relative_to(ROOT / ".local")
            or output.resolve() == ROOT / ".local"
        ):
            parser.error("Output must be a new directory below repository .local")
        result = probe(output, args.wsl) if args.probe else collect(output, args.inputs, args.fetch)
    else:
        plan = check_repository()
        result = {"module_inputs": len(plan["modules"]), "coverage_state": "partial"}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
