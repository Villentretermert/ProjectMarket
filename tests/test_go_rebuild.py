import json
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import pytest

from scripts import go_rebuild as rebuild
from scripts import go_sources as sources


@pytest.fixture
def built(tmp_path: Path) -> tuple[Path, Path]:
    kit, output = tmp_path / "kit", tmp_path / "output"
    shutil.copytree(sources.EVIDENCE, kit)
    output.mkdir()
    runtime = sources.object_json((kit / "runtime.json").read_bytes())
    for role in ("db", "proxy"):
        raw = ("fixture binary " + role).encode()
        (output / role).write_bytes(raw)
        runtime[role]["binary_sha256"] = sources.digest(raw)
        for name in ("go.mod", "go.sum", "build-info.txt", "go-verify.txt"):
            target = f"{role}-verify.txt" if name == "go-verify.txt" else f"{role}-{name}"
            shutil.copyfile(kit / f"{role}-{name}", output / target)
    (kit / "runtime.json").write_bytes(sources.json_bytes(runtime))
    shutil.copyfile(kit / "go-VERSION", output / "toolchain-VERSION")
    shutil.copyfile(kit / "proxy-go-env.json", output / "toolchain-env.json")
    (output / "toolchain-sha256.txt").write_text("a" * 64 + "  /usr/local/go/bin/go\n")
    (output / "initial-state.txt").write_bytes(b"empty-work-volume\n")
    (output / "network-links.txt").write_bytes(b"lo\n")
    (output / "offline-env.json").write_bytes(sources.json_bytes(rebuild.OFFLINE_ENV))
    return kit, output


def test_binaries_and_all_observations_are_checked(built: tuple[Path, Path]) -> None:
    kit, output = built
    result = rebuild.validate_build(kit, output)
    assert set(result["binaries"]) == {"db", "proxy"}
    assert all(b["byte_identical"] for b in result["binaries"].values())


@pytest.mark.parametrize(
    "file",
    [
        "db",
        "proxy",
        "db-build-info.txt",
        "proxy-go.mod",
        "db-go.sum",
        "initial-state.txt",
        "toolchain-VERSION",
        "db-verify.txt",
        "toolchain-sha256.txt",
        "network-links.txt",
        "offline-env.json",
    ],
)
def test_changed_build_artifacts_rejected(built: tuple[Path, Path], file: str) -> None:
    kit, output = built
    (output / file).write_bytes(b"changed")
    with pytest.raises(ValueError):
        rebuild.validate_build(kit, output)


def test_different_compiler_environment_rejected(built: tuple[Path, Path]) -> None:
    kit, output = built
    raw = json.loads((output / "toolchain-env.json").read_bytes())
    raw["CGO_ENABLED"] = "1"
    (output / "toolchain-env.json").write_bytes(sources.json_bytes(raw))
    with pytest.raises(ValueError, match="environment"):
        rebuild.validate_build(kit, output)


def test_inspection_path_is_the_only_ignored_build_metadata() -> None:
    one = b"/out/gosu: go1.26.10\n\tdep\tm\tv1\th1:sum\n"
    two = one.replace(b"/out/gosu", b"/output/db")
    assert rebuild.normalized_build_info(one) == rebuild.normalized_build_info(two)
    assert rebuild.normalized_build_info(one) != rebuild.normalized_build_info(
        two.replace(b"v1", b"v2")
    )
    with pytest.raises(ValueError):
        rebuild.normalized_build_info(b"binary: go1.26.11\n")


def small_plan(kit: Path) -> dict[str, Any]:
    (kit / "module.zip").write_bytes(b"verified zip fixture")
    (kit / "module.mod").write_bytes(b"module example.com/M\n")
    return {
        "modules": [
            {
                "name": "example.com/M",
                "version": "v1.0.0",
                "kind": "zip",
                "filename": "module.zip",
                "h1": "h1:fixture",
            },
            {"name": "example.com/M", "version": "v1.0.0", "kind": "mod", "filename": "module.mod"},
        ]
    }


def test_prepared_cache_is_deterministic_and_contains_no_compiled_cache(
    built: tuple[Path, Path], tmp_path: Path
) -> None:
    kit, _ = built
    plan = small_plan(kit)
    first, second = tmp_path / "a.tar", tmp_path / "b.tar"
    assert rebuild.write_inputs(kit, plan, first) == rebuild.write_inputs(kit, plan, second)
    with tarfile.open(first) as archive:
        names = archive.getnames()
        assert all(n.startswith(("mod/cache/download/", "src/", "probe/")) for n in names)
        assert not any(n.endswith(".info") or "buildcache" in n for n in names)
        stream = archive.extractfile("mod/cache/download/example.com/!m/@v/v1.0.0.ziphash")
        assert stream is not None and stream.read() == b"h1:fixture"
        stream = archive.extractfile("src/proxy/main.go")
        assert stream is not None and stream.read() == (kit / "proxy-main.go").read_bytes()
        assert all(m.mtime == 0 and m.uid == 0 and m.isfile() for m in archive.getmembers())
    with pytest.raises(FileExistsError):
        rebuild.write_inputs(kit, plan, first)


@pytest.mark.parametrize("fault", ["duplicate", "path", "filename", "kind"])
def test_unsafe_cache_mapping_is_rejected(
    built: tuple[Path, Path], tmp_path: Path, fault: str
) -> None:
    kit, _ = built
    plan = small_plan(kit)
    if fault == "duplicate":
        plan["modules"].append(plan["modules"][0])
    elif fault == "path":
        plan["modules"][0]["name"] = "../outside"
    elif fault == "filename":
        plan["modules"][0]["filename"] = "../outside"
    else:
        plan["modules"][0]["kind"] = "info"
    with pytest.raises(ValueError):
        rebuild.write_inputs(kit, plan, tmp_path / "invalid.tar")


@pytest.mark.parametrize("outcome", ["pass", "failure", "timeout"])
def test_container_is_offline_readonly_bounded_and_always_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    calls: list[list[str]] = []

    def invoke(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(args)
        if "--force" in args:
            return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")
        kwargs["stdout"].write(b"fixture output")
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(args, 1)
        return subprocess.CompletedProcess(args, 0 if outcome == "pass" else 1)

    monkeypatch.setattr(subprocess, "run", invoke)
    docker = rebuild.Docker(None)
    if outcome == "pass":
        assert docker.container("owned", [], "true", tmp_path / "run.log") == b"fixture output"
    else:
        with pytest.raises((RuntimeError, subprocess.TimeoutExpired)):
            docker.container("owned", [], "true", tmp_path / "run.log")
    args = calls[0]
    for flag, expected in (
        ("--network", "none"),
        ("--pull", "never"),
        ("--cap-drop", "ALL"),
        ("--cpus", "2"),
        ("--memory", "3g"),
    ):
        assert args[args.index(flag) + 1] == expected
    assert "--read-only" in args
    assert calls[-1] == ["docker", "rm", "--force", "owned"]


def test_corrupt_kit_fails_before_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "manifest.json").write_bytes(b"{}")

    def forbidden(*args: Any) -> None:
        pytest.fail("Docker must not be consulted before source validation")

    monkeypatch.setattr(rebuild, "Docker", forbidden)
    with pytest.raises(ValueError, match="Manifest SHA"):
        rebuild.run(tmp_path, tmp_path / "output", None)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("fault", ["missing_check", "false_check", "duplicate_result", "none"])
def test_runtime_checks_require_every_claim(tmp_path: Path, fault: str) -> None:
    gosu = {"result": "PASS", "nobody": True, "explicit_uid_gid": True, "version": True}
    https = {
        "result": "PASS",
        "https": True,
        "http2": True,
        "untrusted_ca_rejected": True,
        "wrong_hostname_rejected": True,
    }
    (tmp_path / "gosu.log").write_bytes(sources.json_bytes(gosu))
    if fault == "missing_check":
        del https["http2"]
    elif fault == "false_check":
        https["wrong_hostname_rejected"] = False
    raw = json.dumps(https).encode() + b"\n"
    if fault == "duplicate_result":
        raw += raw
    (tmp_path / "gosu.log").write_text(json.dumps(gosu) + "\n")
    (tmp_path / "https.log").write_bytes(b"host warning\n" + raw)
    if fault == "none":
        assert rebuild.runtime_checks(tmp_path)["https"]["http2"] is True
    else:
        with pytest.raises(ValueError):
            rebuild.runtime_checks(tmp_path)
