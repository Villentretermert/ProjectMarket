"""Build and test a recipient-modified psycopg-c in an isolated API image."""

import argparse
import ctypes
import hashlib
import importlib.metadata
import io
import json
import os
import secrets
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
from pathlib import Path
from typing import Any

MARKER = b"marketob-recipient-build-20261107"
ROOT = Path(__file__).resolve().parents[1]
PATCH = (
    "\n/* MarkeTOB replacement demonstration, 2026-11-07.\n"
    " * Added under LGPL-3.0-only, matching this Psycopg source file.\n"
    " * Exposes a test marker without changing the driver interface. */\n"
    '__attribute__((visibility("default")))\n'
    "const char *marketob_recipient_build(void) {\n"
    '    return "' + MARKER.decode() + '";\n}\n'
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(source: bytes, expected_hash: str, context: Path) -> dict[str, Any]:
    """Verify the original archive before creating the explicitly modified tree."""
    if sha256(source) != expected_hash:
        raise ValueError("Original source SHA-256 mismatch")
    context.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(source), mode="r:gz") as archive:
        members = archive.getmembers()
        # This recipe is deliberately scoped to the pinned release.
        for member in members:
            parts = Path(member.name).parts
            if (
                not parts
                or parts[0] != "psycopg_c-3.3.6"
                or ".." in parts
                or "\\" in member.name
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError("Unexpected source archive member")
        archive.extractall(context, filter="data")
    tree = context / "source"
    (context / "psycopg_c-3.3.6").rename(tree)
    changes = []
    for relative in ("psycopg_c/_psycopg.c", "psycopg_c/pq.c"):
        file = tree / relative
        before = file.read_bytes()
        after = before + PATCH.encode()
        file.write_bytes(after)
        changes.append({"path": relative, "before": sha256(before), "after": sha256(after)})
    license_file = tree / "LICENSE.txt"
    if not license_file.is_file():
        raise ValueError("Source license is missing")
    return {
        "source_sha256": expected_hash,
        "marker": MARKER.decode(),
        "license_sha256": sha256(license_file.read_bytes()),
        "changes": changes,
    }


def inspect() -> dict[str, Any]:
    """Hash the environment and call the marker from both loaded C extensions."""
    if sys.platform != "linux":
        raise ValueError("Runtime inspection must run inside the Linux API image")
    import psycopg

    modules = [importlib.import_module(name) for name in ("psycopg_c._psycopg", "psycopg_c.pq")]

    site = Path(psycopg.__file__).resolve().parent.parent
    replacement = importlib.metadata.distribution("psycopg-c")
    replaced = {Path(str(replacement.locate_file(f))).resolve() for f in replacement.files or []}
    other = hashlib.sha256()
    for file in sorted(site.rglob("*")):
        if not file.is_file() or file.suffix == ".pyc" or file.resolve() in replaced:
            continue
        relative = file.relative_to(site).as_posix()
        # Length delimiters make the aggregate unambiguous.
        for part in (relative.encode(), file.read_bytes()):
            other.update(len(part).to_bytes(8, "big"))
            other.update(part)
    extensions = []
    for module in modules:
        assert module.__file__ is not None
        file = Path(module.__file__).resolve()
        library = ctypes.CDLL(str(file), mode=os.RTLD_NOLOAD)
        value: str | None
        try:
            marker = library.marketob_recipient_build
        except AttributeError:
            value = None
        else:
            marker.argtypes = []
            marker.restype = ctypes.c_char_p
            value = marker().decode("ascii")
        extensions.append({"name": file.name, "sha256": sha256(file.read_bytes()), "marker": value})
    packages = subprocess.check_output(["dpkg-query", "-W"])
    return {
        "implementation": psycopg.pq.__impl__,
        "driver_version": psycopg.__version__,
        "extension_version": replacement.version,
        "libpq": psycopg.pq.version(),
        "libpq_build": psycopg.pq.__build_version__,
        "uid": os.getuid(),
        "other_site_packages_sha256": other.hexdigest(),
        "system_packages_sha256": sha256(packages),
        "extensions": extensions,
    }


def compare(before: dict[str, Any], after: dict[str, Any]) -> None:
    for key in (
        "implementation",
        "driver_version",
        "extension_version",
        "libpq",
        "libpq_build",
        "uid",
        "other_site_packages_sha256",
        "system_packages_sha256",
    ):
        if before[key] != after[key]:
            raise ValueError(f"Unexpected change outside replacement: {key}")
    if after["implementation"] != "c" or after["uid"] != 10001 or after["libpq"] != 180006:
        raise ValueError("Unsupported baseline runtime")
    if len(before["extensions"]) != 2 or len(after["extensions"]) != 2:
        raise ValueError("Expected both C extensions")
    for old, new in zip(before["extensions"], after["extensions"], strict=True):
        if (
            old["name"] != new["name"]
            or old["marker"] is not None
            or new["marker"] != MARKER.decode()
            or old["sha256"] == new["sha256"]
        ):
            raise ValueError("Compiled library replacement was not demonstrated")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--api-image", default="marketob-api:local")
    parser.add_argument("--db-image", default="marketob-db:local")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(".local/psycopg-replacement"))
    parser.add_argument("--wsl")
    args = parser.parse_args()
    if args.inspect:
        print(json.dumps(inspect()))
        return
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".local") or output.exists():
        raise ValueError("Output must be a new directory below the repository's .local")
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    package = next(p for p in lock["package"] if p["name"] == "psycopg-c")
    if package["version"] != "3.3.6":
        raise ValueError("Review the replacement recipe for the new driver release")
    expected = package["sdist"]["hash"].removeprefix("sha256:")
    if args.source:
        source = args.source.read_bytes()
    elif args.fetch:
        with urllib.request.urlopen(package["sdist"]["url"], timeout=60) as response:
            source = response.read(package["sdist"]["size"] + 1)
    else:
        raise ValueError("Pass a verified --source archive or --fetch")
    modification = prepare(source, expected, output / "context")
    context = output / "context"
    (output / "original.tar.gz").write_bytes(source)
    (output / "modification.json").write_text(json.dumps(modification, indent=2) + "\n")
    with tarfile.open(output / "modified-source.tar.gz", "w:gz") as archive:
        archive.add(context / "source", arcname="psycopg_c-3.3.6")
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = config["tool"]["uv"]["build-constraint-dependencies"]
    (context / "build-requirements.txt").write_text(
        "".join(r["requirement"] + " --hash=" + r["hashes"][0] + "\n" for r in requirements)
    )
    shutil.copyfile(ROOT / "deploy/replacement/Dockerfile", context / "Dockerfile")
    prefix = ["wsl", "-d", args.wsl, "--exec", "docker"] if args.wsl else ["docker"]

    def docker(*parts: str, source: bytes | None = None, timeout: int = 120) -> str:
        result = subprocess.run(
            prefix + list(parts), input=source, capture_output=True, timeout=timeout
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", "replace"))
        return result.stdout.decode("utf-8", "replace").strip()

    baseline = docker("image", "inspect", args.api_image, "--format", "{{.Id}}")
    database = docker("image", "inspect", args.db_image, "--format", "{{.Id}}")
    unique = secrets.token_hex(8)
    base_tag = "marketob-replacement-base:" + unique
    candidate = "marketob-replacement:" + unique
    program = Path(__file__).read_bytes()

    def inventory(image: str) -> dict[str, Any]:
        data = json.loads(
            docker(
                "run",
                "--rm",
                "-i",
                "--read-only",
                "--network",
                "none",
                "--entrypoint",
                "python",
                image,
                "-",
                "--inspect",
                source=program,
            )
        )
        assert isinstance(data, dict)
        return data

    before = inventory(baseline)
    docker("image", "tag", baseline, base_tag)
    try:
        # Send a small explicit context through stdin; never send .env or the checkout.
        with tarfile.open(output / "context.tar", "w", format=tarfile.GNU_FORMAT) as archive:
            for file in sorted(context.iterdir()):
                archive.add(file, arcname=file.name)
        with (output / "context.tar").open("rb") as stream:
            with (output / "build.log").open("wb") as log:
                subprocess.run(
                    prefix
                    + ["build", "--build-arg", f"API_IMAGE={base_tag}", "-t", candidate, "-"],
                    stdin=stream,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=900,
                    check=True,
                )
        image_id = docker("image", "inspect", candidate, "--format", "{{.Id}}")
        after = inventory(image_id)
        compare(before, after)
        # Reuse the established TLS / pool / cancellation fixture without host ports or user data.
        smoke = [
            sys.executable,
            "-m",
            "scripts.smoke_psycopg",
            "--api-image",
            image_id,
            "--db-image",
            database,
        ]
        if args.wsl:
            smoke += ["--wsl", args.wsl]
        result = subprocess.run(smoke, cwd=ROOT, capture_output=True, timeout=300)
        (output / "smoke.log").write_bytes(result.stdout + result.stderr)
        result.check_returncode()
        linkage = json.loads(
            docker(
                "run",
                "--rm",
                "-i",
                "--read-only",
                "--network",
                "none",
                "--entrypoint",
                "python",
                image_id,
                "-",
                source=(ROOT / "scripts/inspect_psycopg.py").read_bytes(),
            )
        )
        if linkage["status"] != "complete":
            raise ValueError("Replacement linkage is incomplete")
        report = {
            "schema_version": "marketob-library-replacement/v1",
            "result": "PASS",
            "baseline_image": baseline,
            "candidate_image": image_id,
            "candidate_tag": candidate,
            "database_image": database,
            "source_modification": modification,
            "before": before,
            "after": after,
            "linkage": linkage,
            "driver_smoke": json.loads(result.stdout),
        }
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"result": "PASS", "candidate_tag": candidate, "output": str(output)}))
    finally:
        docker("image", "rm", base_tag)


if __name__ == "__main__":
    main()
