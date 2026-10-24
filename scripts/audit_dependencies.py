"""Read-only dependency evidence; scan an allowlisted lockfile copy and immutable images.

Requires an independently installed Trivy. No app packages are installed or updated.
Exit 0: no known advisories, 1: advisories, 2: incomplete check. Licenses need review.
"""

import argparse
import hashlib
import json
import re
import subprocess
import tomllib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = (
    "uv.lock",
    "pyproject.toml",
    "apps/api/pyproject.toml",
    "packages/contracts/pyproject.toml",
    "packages/bot-sdk/pyproject.toml",
    "bots/pilot/pyproject.toml",
    "apps/client/package.json",
    "apps/client/package-lock.json",
    "deploy/Dockerfile",
    "deploy/Dockerfile.bot",
    "deploy/Dockerfile.proxy",
    "compose.yaml",
)


def normalized_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def stage_inputs(root: Path, target: Path) -> dict[str, Any]:
    """No env files, source, node_modules, backups or user payloads enter the scanner."""
    target.mkdir(parents=True, exist_ok=False)
    sources = []
    for relative in MANIFESTS:
        original = root / relative
        copy = target / relative
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(original.read_bytes())
        sources.append({"path": relative, "sha256_lf_normalized": normalized_hash(original)})
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    python = {(p["name"], p["version"]) for p in lock["package"] if "registry" in p["source"]}
    # Include explicit build tool pins, even though they are not workspace dependencies.
    build = set()
    for relative in MANIFESTS:
        if relative.endswith("pyproject.toml"):
            data = tomllib.loads((root / relative).read_text(encoding="utf-8"))
            for requirement in data.get("build-system", {}).get("requires", []):
                match = re.fullmatch(r"([\w.-]+)==([\w.+-]+)", requirement)
                if not match:
                    raise ValueError("Build requirement is not exactly pinned")
                build.add((match[1], match[2]))
        if "Dockerfile" in relative:
            build.update(re.findall(r"\b(uv)==([\d.]+)", (root / relative).read_text()))
    # All platform/dev entries are included, not just packages installed on this machine.
    pins = sorted(python | build)
    (target / "requirements.txt").write_text(
        "".join(f"{name}=={version}\n" for name, version in pins), encoding="utf-8"
    )
    node = json.loads((root / "apps/client/package-lock.json").read_text())
    npm = sorted(
        {
            (p.get("name") or key.rsplit("node_modules/", 1)[-1], p["version"])
            for key, p in node["packages"].items()
            if key
        }
    )
    return {
        "sources": sources,
        "python": pins,
        "npm": npm,
        "explicit_build_tools": sorted(build),
        "local_packages": sorted(
            p["name"] for p in lock["package"] if "registry" not in p["source"]
        ),
    }


def license_metadata(package: tuple[str, str]) -> dict[str, Any]:
    name, version = package
    url = f"https://pypi.org/pypi/{quote(name, safe='')}/{quote(version, safe='')}/json"
    result: dict[str, Any] = {"name": name, "version": version, "source": url}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "MarkeTOB-dependency-review"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
        info = data["info"]
        if info["version"] != version or not data.get("urls"):
            raise ValueError("Release metadata mismatch")
        # Preserve declared metadata, not an inferred legal compatibility decision.
        expression = info.get("license_expression")
        legacy = info.get("license") or ""
        classifiers = [c for c in info.get("classifiers", []) if c.startswith("License ::")]
        result.update(
            {
                "status": "declared" if expression or legacy or classifiers else "unknown",
                "expression": expression,
                "legacy_short": legacy if len(legacy) <= 200 else None,
                "legacy_text_sha256": hashlib.sha256(legacy.encode()).hexdigest()
                if legacy
                else None,
                "classifiers": classifiers,
                "pypi_advisory_ids": [
                    v["id"] for v in data.get("vulnerabilities", []) if not v.get("withdrawn")
                ],
            }
        )
    except urllib.error.URLError, TimeoutError, ValueError, KeyError:
        result["status"] = "unavailable"
    return result


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    packages, findings, licenses = [], [], []
    if "Results" not in report:
        raise ValueError("Scanner returned no component results")
    for group in report["Results"]:
        context = {"target": group["Target"], "type": group.get("Type")}
        for package in group.get("Packages") or []:
            packages.append(
                context
                | {
                    "name": package["Name"],
                    "version": package.get("Version"),
                    "licenses": package.get("Licenses", []),
                }
            )
        for finding in group.get("Vulnerabilities") or []:
            findings.append(
                context
                | {
                    key: finding.get(key)
                    for key in (
                        "VulnerabilityID",
                        "PkgName",
                        "InstalledVersion",
                        "FixedVersion",
                        "Severity",
                        "Status",
                        "PrimaryURL",
                        "DataSource",
                        "SeveritySource",
                    )
                }
            )
        for license_entry in group.get("Licenses") or []:
            licenses.append(
                context
                | {
                    key: license_entry.get(key)
                    for key in (
                        "PkgName",
                        "Name",
                        "Category",
                        "Severity",
                        "Confidence",
                    )
                }
            )
    return {"packages": packages, "findings": findings, "licenses": licenses}


def check_coverage(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for ecosystem, types in (("python", {"pip", "uv"}), ("npm", {"npm"})):
        found = {(p["name"], p["version"]) for p in actual["packages"] if p["type"] in types}
        missing.extend(
            f"{ecosystem}:{name}@{version}"
            for name, version in expected[ecosystem]
            if (name, version) not in found
        )
    return missing


def exit_status(report: dict[str, Any]) -> int:
    if report["missing_packages"] or any(
        p["status"] == "unavailable" for p in report["python_licenses"]
    ):
        return 2
    if any(item["findings"] for item in report["targets"]):
        return 1
    if any(p["pypi_advisory_ids"] for p in report["python_licenses"]):
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trivy", required=True, help="Executable path, relative to repo or absolute"
    )
    parser.add_argument("--wsl", help="Run Trivy and Docker through this WSL distro")
    parser.add_argument(
        "--image", action="append", default=[], help="Existing local image; repeatable"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="New output directory below repo"
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output.exists():
        parser.error("Output must be a new directory below the repository")
    output.mkdir(parents=True)
    prefix = ["wsl", "-d", args.wsl, "--"] if args.wsl else []

    def path_arg(path: Path) -> str:
        return path.relative_to(ROOT).as_posix()

    def run(arguments: list[str]) -> str:
        completed = subprocess.run(
            prefix + arguments,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=900,
        )
        with (output / "scanner.log").open("a", encoding="utf-8") as log:
            log.write(completed.stderr)
        if completed.returncode:
            raise RuntimeError("Scanner command failed; see private scanner.log")
        return completed.stdout

    try:
        inputs = stage_inputs(ROOT, output / "inputs")
        trivy = args.trivy.replace("\\", "/")
        common = [
            "--cache-dir",
            ".local/trivy-cache",
            "--config",
            "",
            "--quiet",
            "--disable-telemetry",
            "--skip-version-check",
            "--parallel",
            "2",
            "--timeout",
            "10m",
            "--ignorefile",
            "",
            "--scanners",
            "vuln,license",
            "--format",
            "json",
        ]
        lockfile = output / "locks.raw.json"
        run(
            [
                trivy,
                "fs",
                *common,
                "--include-dev-deps",
                "--output",
                path_arg(lockfile),
                path_arg(output / "inputs"),
            ]
        )
        locks = summarize(json.loads(lockfile.read_text(encoding="utf-8")))
        report: dict[str, Any] = {
            "schema_version": 1,
            "started_from_commit": run(["git", "rev-parse", "HEAD"]).strip(),
            "inputs": inputs,
            "targets": [{"name": "locked-dependencies", **locks}],
            "missing_packages": check_coverage(inputs, locks),
            "limitations": [
                "Known advisories only; no exploitability or legal compliance verdict",
                "Build tool transitives, browser binaries, Android and developer OS excluded",
                "Local project packages are not public dependencies; source review is separate",
                "Image licenses from package metadata; no full source/header license scan",
            ],
        }
        with ThreadPoolExecutor(max_workers=4) as pool:
            report["python_licenses"] = list(pool.map(license_metadata, inputs["python"]))
        for index, image in enumerate(args.image):
            # Resolve once, then scan the immutable image ID; never containers or volumes.
            inspected = json.loads(run(["docker", "image", "inspect", image]))[0]
            identity = inspected["Id"]
            raw = output / f"image-{index}.raw.json"
            run(
                [
                    trivy,
                    "image",
                    *common,
                    "--image-src",
                    "docker",
                    "--output",
                    path_arg(raw),
                    identity,
                ]
            )
            scan = json.loads(raw.read_text(encoding="utf-8"))
            if scan.get("Metadata", {}).get("ImageID") != identity:
                raise ValueError("Image identity does not match scanner result")
            sbom = output / f"image-{index}.cdx.json"
            run(
                [
                    trivy,
                    "convert",
                    "--format",
                    "cyclonedx",
                    "--output",
                    path_arg(sbom),
                    path_arg(raw),
                ]
            )
            report["targets"].append(
                {
                    "name": image,
                    "image_id": identity,
                    "os": scan.get("Metadata", {}).get("OS"),
                    **summarize(scan),
                }
            )
        report["scanner"] = json.loads(
            run([trivy, "--cache-dir", ".local/trivy-cache", "version", "--format", "json"])
        )
        report["completed_at"] = datetime.now(UTC).isoformat()
        report["exit_status"] = exit_status(report)
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "output": path_arg(output),
                    "exit_status": report["exit_status"],
                    "missing": report["missing_packages"],
                    "targets": [
                        {
                            "name": t["name"],
                            "packages": len(t["packages"]),
                            "findings": len(t["findings"]),
                        }
                        for t in report["targets"]
                    ],
                }
            )
        )
        return int(report["exit_status"])
    except (RuntimeError, ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        (output / "INCOMPLETE.txt").write_text(
            type(error).__name__ + ": check scanner.log; audit not complete\n"
        )
        print(
            "Dependency audit incomplete; check the private output directory. No release verdict."
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
