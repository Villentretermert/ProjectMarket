"""The handover verifier must work offline and reject misleading archive layouts."""

import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

from scripts.delivery_bundle import ROOT, check_recipe, file_hash, git_snapshot, pack, verify


def identity() -> dict[str, Any]:
    return {
        "release_commit": "a" * 40,
        "tooling_commit": "b" * 40,
        "coverage_state": "partial",
        "open_items": ["review"],
        "images": {role: "sha256:" + "c" * 64 for role in ("api", "bot", "db", "proxy")},
    }


def kit(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    source = tmp_path / "source"
    source.write_bytes(b"reviewed source\n")
    path = tmp_path / "kit.tar"
    result = pack(path, {"sources/input.tar": source}, identity())
    return path, result


def altered(tmp_path: Path, failure: str) -> Path:
    original, result = kit(tmp_path)
    manifest = result["manifest"]
    if failure == "unsafe_path":
        manifest["files"][0]["name"] = "../escape"
    elif failure == "duplicate_row":
        manifest["files"].append(manifest["files"][0])
    elif failure == "false_complete":
        manifest["coverage_state"] = "complete"
    elif failure == "wrong_images":
        manifest["images"].pop("api")
    raw = json.dumps(manifest).encode()
    if failure == "duplicate_json":
        raw = raw[:-1] + b', "files": []}'
    path = tmp_path / "altered.tar"
    with tarfile.open(path, "w") as archive:
        header = tarfile.TarInfo("manifest.json")
        header.size = len(raw)
        archive.addfile(header, io.BytesIO(raw))
        with tarfile.open(original) as before:
            member = before.getmember("sources/input.tar")
            source = before.extractfile(member)
            assert source is not None
            data = source.read()
            if failure == "missing":
                return path
            if failure == "corrupt":
                data = b"x" + data[1:]
            if failure == "link":
                member.type, member.linkname, member.size = tarfile.SYMTYPE, "/etc/passwd", 0
            if failure == "unexpected":
                member.name = "extra"
            archive.addfile(member, io.BytesIO(data))
            if failure == "duplicate":
                archive.addfile(member, io.BytesIO(data))
    return path


def test_round_trip_and_no_overwrite(tmp_path: Path) -> None:
    path, result = kit(tmp_path)
    manifest = verify(path, result["sha256"])
    assert manifest["coverage_state"] == "partial"
    assert manifest["open_items"] == ["review"]
    with pytest.raises(FileExistsError):
        pack(path, {}, identity())


def test_external_digest_binds_whole_archive(tmp_path: Path) -> None:
    path, result = kit(tmp_path)
    with path.open("ab") as stream:
        stream.write(b"unreviewed trailing content")
    with pytest.raises(ValueError, match="Whole archive"):
        verify(path, result["sha256"])


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "corrupt",
        "link",
        "unexpected",
        "duplicate",
        "unsafe_path",
        "duplicate_row",
        "false_complete",
        "wrong_images",
        "duplicate_json",
    ],
)
def test_invalid_layout_even_with_recomputed_outer_hash(tmp_path: Path, failure: str) -> None:
    path = altered(tmp_path, failure)
    with pytest.raises(ValueError):
        verify(path, file_hash(path))


def test_verifier_runs_standalone_without_checkout(tmp_path: Path) -> None:
    path, result = kit(tmp_path)
    standalone = tmp_path / "verify_bundle.py"
    shutil.copyfile(ROOT / "scripts/delivery_bundle.py", standalone)
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            str(standalone),
            "--verify",
            str(path),
            "--sha256",
            result["sha256"],
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    assert json.loads(process.stdout)["integrity"] == "verified"


def test_release_recipe_binds_current_evidence() -> None:
    recipe = check_recipe()
    assert recipe["release_commit"] == "68958f1bba16df49159d13fd9e99b47f7d924956"
    assert len(recipe["sources"]) == 4


def test_current_recipe_preserves_historical_source_inputs() -> None:
    current = check_recipe(recipe_path="third_party/delivery-schema-20261109/recipe.json")
    previous = check_recipe()
    assert current["release_commit"] == "896449bde9cdec4cea9f7ce29eba6910285da30e"
    assert current["sources"] == previous["sources"]
    assert current["images"]["api"] != previous["images"]["api"]
    assert current["archive"] == "marketob-sources-schema-20261109.tar"


@pytest.mark.parametrize("change", ["image", "commit", "gaps", "path", "missing", "sources"])
def test_current_recipe_rejects_stale_or_unbound_metadata(
    tmp_path: Path, change: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.delivery_bundle as module

    path = ROOT / "third_party/delivery-schema-20261109/recipe.json"
    recipe = json.loads(path.read_bytes())
    if change == "image":
        recipe["images"]["api"] = "sha256:" + "0" * 64
    elif change == "commit":
        recipe["release_commit"] = "0" * 40
    elif change == "gaps":
        recipe["open_items"] = ["hidden"]
    elif change == "path":
        recipe["archive"] = "../escape.tar"
    elif change == "missing":
        del recipe["release_binding"]
    else:
        recipe["sources"][0]["sha256"] = "0" * 64
    # Use real material verification while substituting only the recipe under review.
    original = module.json_object
    raw = path.read_bytes()
    monkeypatch.setattr(
        module, "json_object", lambda data: recipe if data == raw else original(data)
    )
    with pytest.raises(ValueError):
        check_recipe(recipe_path=path.relative_to(ROOT).as_posix())


def test_git_snapshot_ignores_windows_checkout_conversion(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    args = [
        "git",
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "core.hooksPath=disabled-hooks",
    ]

    def git(*parts: str) -> bytes:
        return subprocess.check_output(
            args + list(parts), cwd=repository, stderr=subprocess.DEVNULL
        )

    git("init")
    git("config", "core.autocrlf", "true")
    (repository / "source.txt").write_bytes(b"line one\nline two\n")
    git("add", "source.txt")
    git("commit", "-m", "fixture")
    (repository / ".env").write_bytes(b"local-only")
    target = tmp_path / "snapshot.tar"
    assert git_snapshot(repository, git("rev-parse", "HEAD").decode().strip(), target) == 1
    with tarfile.open(target) as archive:
        assert archive.getnames() == ["source.txt"]
        source = archive.extractfile("source.txt")
        assert source is not None and source.read() == b"line one\nline two\n"
