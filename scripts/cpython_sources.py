"""Bind CPython sources to recorded immutable-image observations; verify offline.

Only stdlib is needed by the delivered verifier. Observed build flags and hashes
do not prove binary reproducibility. Source/build files are read, never executed.
"""

import argparse
import base64
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "third_party/cpython-schema-20261109"
INVENTORY = "third_party/schema-20261109/inventory.json"
RECIPE = "third_party/delivery-schema-20261109/recipe.json"
TEXTS = {
    "license": "LICENSE.txt",
    "patchlevel": "patchlevel.h",
    "pyconfig": "pyconfig.h",
    "makefile": "Makefile",
}
GAPS = [
    "compiler-and-build-dependencies",
    "go-inputs",
    "native-link-and-rebuild",
    "release-acceptance",
]
SOURCE_LIMIT = 100_000_000
PROBE = r"""
import base64,hashlib,json,pathlib,platform,sys,sysconfig
paths={'executable':pathlib.Path(sys.executable).resolve(),
       'library':pathlib.Path(sysconfig.get_config_var('LIBDIR'))/sysconfig.get_config_var('LDLIBRARY'),
       'license':pathlib.Path(sysconfig.get_path('stdlib'))/'LICENSE.txt',
       'patchlevel':pathlib.Path(sysconfig.get_path('include'))/'patchlevel.h',
       'pyconfig':pathlib.Path(sysconfig.get_config_h_filename()),
       'makefile':pathlib.Path(sysconfig.get_makefile_filename())}
files={key:{'path':str(path),'size':path.stat().st_size,
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for key,path in paths.items()}
texts={key:base64.b64encode(path.read_bytes()).decode() for key,path in paths.items()
       if key in ('license','patchlevel','pyconfig','makefile')}
print(json.dumps({'version':platform.python_version(),'implementation':platform.python_implementation(),
 'machine':platform.machine(),'compiler':platform.python_compiler(),
 'config_args':sysconfig.get_config_var('CONFIG_ARGS'),'files':files,'texts':texts}))
"""


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


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


def file_spec(path: Path) -> dict[str, Any]:
    return {"size": path.stat().st_size, "sha256": file_digest(path)}


def validate_plan(plan: dict[str, Any], directory: Path) -> None:
    if (
        plan["schema"] != "marketob-cpython-source/v1"
        or plan["coverage_state"] != "partial"
        or plan["open_items"] != GAPS
        or not re.fullmatch(r"[0-9a-f]{40}", plan["release_commit"])
    ):
        raise ValueError("Invalid source plan or coverage claim")
    inventory_raw, runtime_raw = (
        (directory / "inventory.json").read_bytes(),
        (directory / "runtime.json").read_bytes(),
    )
    if (
        digest(inventory_raw) != plan["inventory_sha256"]
        or digest(runtime_raw) != plan["runtime_sha256"]
    ):
        raise ValueError("Source evidence hash mismatch")
    inventory, runtime = object_json(inventory_raw), object_json(runtime_raw)
    images = {row["role"]: row for row in inventory["images"]}
    if (
        len(images) != 4
        or len(inventory["images"]) != 4
        or set(images) != {"api", "bot", "db", "proxy"}
    ):
        raise ValueError("Expected four inventory image roles")
    if set(runtime) != {"api", "bot"} or set(plan["images"]) != {"api", "bot"}:
        raise ValueError("Missing CPython image role")
    source = plan["source"]
    version = source["version"]
    if not re.fullmatch(r"3\.\d+\.\d+", version):
        raise ValueError("Expected stable Python version")
    filename = f"Python-{version}.tar.xz"
    if (
        source["filename"] != filename
        or source["url"] != f"https://www.python.org/ftp/python/{version}/{filename}"
        or source["release_url"]
        != "https://www.python.org/downloads/release/python-" + version.replace(".", "") + "/"
        or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"])
        or source["published_sha256"] != source["sha256"]
        or type(source["size"]) is not int
        or not 0 < source["size"] <= SOURCE_LIMIT
    ):
        raise ValueError("Invalid official source identity")
    for role, observation in runtime.items():
        image = images[role]
        if (
            not re.fullmatch(r"sha256:[0-9a-f]{64}", image["id"])
            or image["id"] != plan["images"][role]
            or observation["image_id"] != image["id"]
            or (image["os"], image["architecture"]) != ("linux", "amd64")
        ):
            raise ValueError("Image identity or platform mismatch")
        entries = [
            p for p in image["components"] if p["ecosystem"] == "runtime" and p["name"] == "CPython"
        ]
        if len(entries) != 1 or entries[0]["version"] != version:
            raise ValueError("Installed CPython inventory mismatch")
        if (
            observation["implementation"] != "CPython"
            or observation["version"] != version
            or observation["machine"] != "x86_64"
            or observation["source_env"]
            != {"PYTHON_VERSION": version, "PYTHON_SHA256": source["sha256"]}
            or not observation["compiler"]
            or not observation["config_args"]
            or set(observation["files"]) != set(TEXTS) | {"executable", "library"}
        ):
            raise ValueError("Runtime version/source evidence mismatch")
        for key, spec in observation["files"].items():
            if (
                not re.fullmatch(r"[0-9a-f]{64}", spec["sha256"])
                or not 0 < spec["size"] <= SOURCE_LIMIT
            ):
                raise ValueError("Invalid observed file hash/size")
            if key in TEXTS and file_spec(directory / TEXTS[key]) != {
                k: spec[k] for k in ("size", "sha256")
            }:
                raise ValueError("Observed text bytes changed")
        license_spec = observation["files"]["license"]
        if not any(
            n["source_path"] == license_spec["path"] and n["sha256"] == license_spec["sha256"]
            for n in entries[0]["notices"]
        ):
            raise ValueError("License differs from installed notice inventory")
    if {k: v for k, v in runtime["api"].items() if k != "image_id"} != {
        k: v for k, v in runtime["bot"].items() if k != "image_id"
    }:
        raise ValueError("API/bot CPython observations diverge")


def verify_source(path: Path, plan: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    source = plan["source"]
    if file_spec(path) != {key: source[key] for key in ("size", "sha256")}:
        raise ValueError("CPython source size/SHA-256 mismatch")
    root = "Python-" + source["version"]
    wanted = {root + "/LICENSE": "license", root + "/Include/patchlevel.h": "patchlevel"}
    found: dict[str, str] = {}
    seen: set[str] = set()
    expanded = 0
    with tarfile.open(path, mode="r|xz") as archive:
        for index, member in enumerate(archive):
            name = member.name.rstrip("/") if member.isdir() else member.name
            parts = PurePosixPath(name).parts
            if (
                not parts
                or parts[0] != root
                or ".." in parts
                or "\\" in name
                or ":" in name
                or str(PurePosixPath(name)) != name
            ):
                raise ValueError("Unexpected CPython archive path")
            if name in seen or index >= 50_000:
                raise ValueError("Duplicate or excessive source members")
            seen.add(name)
            expanded += member.size
            if member.size > SOURCE_LIMIT or expanded > 500_000_000:
                raise ValueError("Oversized CPython source contents")
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise ValueError("Unsupported CPython source member type")
            if name in wanted:
                if not member.isfile() or member.size > 1_000_000:
                    raise ValueError("Invalid source evidence member")
                stream = archive.extractfile(member)
                assert stream is not None
                raw, key = stream.read(), wanted[name]
                if digest(raw) != runtime["api"]["files"][key]["sha256"]:
                    raise ValueError("Source LICENSE/patchlevel differs from runtime")
                if key == "patchlevel":
                    versions = re.findall(rb'^#define\s+PY_VERSION\s+"([^"]+)"', raw, re.M)
                    if versions != [source["version"].encode()]:
                        raise ValueError("Source patchlevel version mismatch")
                found[key] = digest(raw)
    if set(found) != set(wanted.values()):
        raise ValueError("Missing source LICENSE/patchlevel")
    return {"members": len(seen), "expanded_bytes": expanded, "matched_source_files": found}


def verify(directory: Path, expected_manifest_sha256: str) -> dict[str, Any]:
    manifest_path = directory / "manifest.json"
    if (
        not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256)
        or file_digest(manifest_path) != expected_manifest_sha256
    ):
        raise ValueError("External manifest SHA-256 mismatch")
    manifest = object_json(manifest_path.read_bytes())
    if manifest["schema"] != "marketob-cpython-kit/v1":
        raise ValueError("Invalid source kit schema")
    for name, spec in manifest["files"].items():
        if PurePosixPath(name).name != name or name in (".", "..") or "\\" in name or ":" in name:
            raise ValueError("Unsafe source kit filename")
        path = directory / name
        if path.is_symlink() or not path.is_file() or file_spec(path) != spec:
            raise ValueError("Source kit file size/hash mismatch")
    if {p.name for p in directory.iterdir()} != set(manifest["files"]) | {"manifest.json"}:
        raise ValueError("Missing or unexpected source kit files")
    plan = object_json((directory / "source-plan.json").read_bytes())
    required = {
        "source-plan.json",
        "inventory.json",
        "runtime.json",
        "verify.py",
        "README.md",
        plan["source"]["filename"],
    } | set(TEXTS.values())
    if set(manifest["files"]) != required:
        raise ValueError("Incomplete source kit coverage")
    validate_plan(plan, directory)
    runtime = object_json((directory / "runtime.json").read_bytes())
    result = verify_source(directory / plan["source"]["filename"], plan, runtime)
    return {
        "manifest_sha256": expected_manifest_sha256,
        "images": plan["images"],
        "source": plan["source"],
        "coverage_state": "partial",
        "open_items": GAPS,
        **result,
    }


def check_repository() -> dict[str, Any]:
    plan = object_json((EVIDENCE / "source-plan.json").read_bytes())
    recipe = object_json((ROOT / RECIPE).read_bytes())
    if (
        plan["release_commit"] != recipe["release_commit"]
        or plan["inventory_sha256"] != recipe["bound_files"][INVENTORY]
        or plan["images"] != {r: recipe["images"][r] for r in ("api", "bot")}
        or file_digest(ROOT / INVENTORY) != plan["inventory_sha256"]
    ):
        raise ValueError("CPython plan differs from release binding")
    validate_plan(plan, EVIDENCE)
    return plan


def collect(output: Path, source: Path | None, fetch: bool) -> dict[str, Any]:
    plan = check_repository()
    output.mkdir(parents=True, exist_ok=False)
    try:
        for name in (
            "source-plan.json",
            "runtime.json",
            "inventory.json",
            "README.md",
            *TEXTS.values(),
        ):
            shutil.copyfile(EVIDENCE / name, output / name)
        # Normalize only our verifier text; upstream observations remain byte-exact.
        (output / "verify.py").write_bytes(Path(__file__).read_bytes().replace(b"\r\n", b"\n"))
        target = output / plan["source"]["filename"]
        if source:
            shutil.copyfile(source, target)
        elif fetch:
            with urllib.request.urlopen(plan["source"]["url"], timeout=40) as response:
                if response.url != plan["source"]["url"]:
                    raise ValueError("Unexpected CPython download redirect")
                raw = response.read(plan["source"]["size"] + 1)
            target.write_bytes(raw)
        else:
            raise ValueError("Pass --source or --fetch")
        verify_source(target, plan, object_json((output / "runtime.json").read_bytes()))
        manifest = {
            "schema": "marketob-cpython-kit/v1",
            "files": {p.name: file_spec(p) for p in sorted(output.iterdir())},
        }
        (output / "manifest.json").write_bytes(json_bytes(manifest))
        return verify(output, file_digest(output / "manifest.json"))
    except Exception:
        (output / "INCOMPLETE.txt").write_text(
            "Incomplete CPython source kit; do not distribute.\n"
        )
        raise


def probe(output: Path, wsl: str | None) -> None:
    recipe = object_json((ROOT / RECIPE).read_bytes())
    prefix = ["wsl", "-d", wsl, "--exec", "docker"] if wsl else ["docker"]
    records = {}
    output.mkdir(parents=True, exist_ok=False)
    for role in ("api", "bot"):
        image = recipe["images"][role]
        config = json.loads(
            subprocess.check_output(
                prefix + ["image", "inspect", "--format", "{{json .Config.Env}}", image]
            )
        )
        env = {
            s.split("=", 1)[0]: s.split("=", 1)[1]
            for s in config
            if s.split("=", 1)[0] in ("PYTHON_VERSION", "PYTHON_SHA256")
        }
        data = object_json(
            subprocess.check_output(
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
                    "/usr/local/bin/python",
                    image,
                    "-I",
                    "-c",
                    PROBE,
                ]
            )
        )
        for key, encoded in data.pop("texts").items():
            raw = base64.b64decode(encoded, validate=True)
            spec = data["files"][key]
            if digest(raw) != spec["sha256"] or len(raw) != spec["size"]:
                raise ValueError("Probe text hash mismatch")
            path = output / TEXTS[key]
            if path.exists() and path.read_bytes() != raw:
                raise ValueError("API/bot observed text differs")
            path.write_bytes(raw)
        records[role] = {"image_id": image, "source_env": env, **data}
    (output / "runtime.json").write_bytes(json_bytes(records))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-plan", action="store_true")
    mode.add_argument("--verify", type=Path)
    mode.add_argument("--collect", type=Path)
    mode.add_argument("--probe", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--wsl")
    args = parser.parse_args()
    if args.verify:
        if not args.sha256:
            parser.error("--verify requires an independently supplied manifest --sha256")
        result = verify(args.verify, args.sha256)
    elif args.collect or args.probe:
        path = args.collect or args.probe
        if not path.resolve().is_relative_to(ROOT / ".local") or path.resolve() == ROOT / ".local":
            parser.error("Output must be a new directory below repository .local")
        if args.probe:
            probe(path, args.wsl)
            result = {"probed_roles": ["api", "bot"]}
        else:
            result = collect(path, args.source, args.fetch)
    else:
        plan = check_repository()
        result = {
            "version": plan["source"]["version"],
            "roles": sorted(plan["images"]),
            "coverage_state": "partial",
        }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
