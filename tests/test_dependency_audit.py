"""Audit evidence must include dev/platform dependencies and never turn gaps green."""

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.audit_dependencies import ROOT, check_coverage, exit_status, stage_inputs, summarize


def test_staging_excludes_private_files_and_includes_build_and_optional_packages(
    tmp_path: Path,
) -> None:
    staged = tmp_path / "inputs"
    expected = stage_inputs(ROOT, staged)
    assert ("fsevents", "2.3.2") in expected["npm"]
    assert ("uv", "0.13.5") in expected["python"]
    assert ("hatchling", "1.32.4") in expected["python"]
    assert len(expected["local_packages"]) == 5
    paths = {p.relative_to(staged).as_posix() for p in staged.rglob("*") if p.is_file()}
    assert paths == {p["path"] for p in expected["sources"]} | {"requirements.txt"}
    assert all(not path.startswith((".local/", ".env", ".git/")) for path in paths)
    # Reusing old inputs must not retain removed dependencies or hide a failed refresh.
    with pytest.raises(FileExistsError):
        stage_inputs(ROOT, staged)


def test_missing_optional_or_development_dependency_is_a_coverage_failure() -> None:
    missing = check_coverage(
        {"python": [("pytest", "9.1.1")], "npm": [("fsevents", "2.3.2")]},
        {"packages": [{"type": "pip", "name": "pytest", "version": "9.1.1"}]},
    )
    assert missing == ["npm:fsevents@2.3.2"]


def test_summary_keeps_unfixed_and_unknown_severity_findings() -> None:
    raw = {
        "Results": [
            {
                "Target": "os",
                "Type": "debian",
                "Packages": [{"Name": "libx", "Version": "1.0", "Licenses": ["GPL-2.0"]}],
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "TEST-1",
                        "PkgName": "libx",
                        "Severity": "UNKNOWN",
                        "Status": "will_not_fix",
                    }
                ],
            }
        ]
    }
    report = summarize(raw)
    assert report["findings"][0]["Status"] == "will_not_fix"
    assert report["findings"][0]["FixedVersion"] is None
    assert report["packages"][0]["licenses"] == ["GPL-2.0"]
    with pytest.raises(ValueError, match="no component"):
        summarize({"SchemaVersion": 2})


def test_unversioned_image_component_is_preserved_as_unknown() -> None:
    result = summarize(
        {"Results": [{"Target": "binary", "Type": "gobinary", "Packages": [{"Name": "main"}]}]}
    )
    assert result["packages"][0]["version"] is None


@pytest.mark.parametrize(
    "failure, expected", [("finding", 1), ("missing", 2), ("metadata", 2), ("pypi", 1), ("none", 0)]
)
def test_advisories_and_incomplete_checks_are_not_success(failure: str, expected: int) -> None:
    report: dict[str, Any] = {
        "targets": [{"findings": []}],
        "missing_packages": [],
        "python_licenses": [{"status": "declared", "pypi_advisory_ids": []}],
    }
    if failure == "finding":
        report["targets"][0]["findings"] = [{"Severity": "CRITICAL"}]
    elif failure == "missing":
        report["missing_packages"] = ["npm:missing@1"]
    elif failure == "metadata":
        report["python_licenses"][0]["status"] = "unavailable"
    elif failure == "pypi":
        report["python_licenses"][0]["pypi_advisory_ids"] = ["PYSEC-TEST"]
    assert exit_status(json.loads(json.dumps(report))) == expected
