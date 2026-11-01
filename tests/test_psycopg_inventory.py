"""Native wheel evidence must not confuse installed, loaded and system libraries."""

from pathlib import Path

import pytest

from scripts import inspect_psycopg


def test_loaded_wheel_is_distinct_from_system_and_unloaded_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = [
        tmp_path / name for name in ("libpq-test.dll", "libssl-test.dll", "libcrypto-test.dll")
    ]
    for path in paths:
        path.write_bytes(b"fixture native image")
    system = tmp_path / "system" / "libcrypto-test.dll"
    unused = tmp_path / "unused" / "libcrypto-test.dll"
    queried: list[Path] = []

    def version(path: Path) -> str:
        queried.append(path)
        return "OpenSSL 3.5.8 25 Aug 2026"

    monkeypatch.setattr(inspect_psycopg, "openssl_version", version)
    result = inspect_psycopg.collect_loaded(
        [*(str(path) for path in paths), str(system), str(paths[0])], set(paths) | {unused}
    )
    assert result["gaps"] == []
    assert queried == [paths[2]]
    assert len(result["libraries"]) == 3
    assert all(len(item["sha256"]) == 64 for item in result["libraries"])
    assert all("path" not in item for item in result["libraries"])


def test_disk_copy_and_relative_loader_name_cannot_establish_linkage(tmp_path: Path) -> None:
    result = inspect_psycopg.collect_loaded(["libcrypto-relative.so"], {tmp_path / "libcrypto.so"})
    assert result["libraries"] == []
    assert "unresolved_loaded_path:libcrypto" in result["gaps"]
    assert "expected_one_loaded_libcrypto:found_0" in result["gaps"]


def test_failed_version_read_keeps_gap_without_private_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    crypto = tmp_path / "libcrypto-fixture.so"
    crypto.write_bytes(b"fixture")

    def unavailable(path: Path) -> str:
        raise OSError(f"Cannot open {path}")

    monkeypatch.setattr(inspect_psycopg, "openssl_version", unavailable)
    result = inspect_psycopg.collect_loaded([str(crypto)], {crypto})
    assert "unreadable_loaded_library:libcrypto" in result["gaps"]
    assert str(tmp_path) not in str(result)


@pytest.mark.parametrize("status, code", [("complete", 0), ("incomplete", 2)])
def test_cli_preserves_incomplete_inventory_exit_code(
    status: str, code: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(inspect_psycopg, "inspect_runtime", lambda: {"status": status})
    assert inspect_psycopg.main() == code
    assert status in capsys.readouterr().out


@pytest.mark.parametrize("linked", [True, False])
def test_system_inventory_requires_extension_dependency_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, linked: bool
) -> None:
    paths = [tmp_path / name for name in ("libpq.so.5.18", "libssl.so.3", "libcrypto.so.3")]
    for path in paths:
        path.write_bytes(b"system library fixture")

    def output(*args: str) -> str:
        if args[0] == "ldd":
            return "\n".join(f"{path.name} => {path} (0x0)" for path in paths) if linked else ""
        if args[1] == "-W":
            return "18.6-1.pgdg12+2" if args[-1] == "libpq5" else "3.0.22-1~deb12u2"
        return "\n".join(str(path) for path in (paths[:1] if args[-1] == "libpq5" else paths[1:]))

    monkeypatch.setattr(inspect_psycopg, "command_output", output)
    monkeypatch.setattr(inspect_psycopg, "openssl_version", lambda path: "OpenSSL 3.0.22")
    # Linux ldd absolute-path syntax is intentionally platform specific.
    if not str(tmp_path).startswith("/"):
        pytest.skip("Linux loader syntax")
    result = inspect_psycopg.collect_system([str(path) for path in paths], [tmp_path / "pq.so"])
    if linked:
        assert result["gaps"] == []
        assert {item["owner"] for item in result["libraries"]} == {"libpq5", "libssl3"}
        unknown = str(tmp_path / "libcrypto-unowned.so")
        result = inspect_psycopg.collect_system(
            [*(str(path) for path in paths), unknown], [tmp_path / "pq.so"]
        )
        assert "unexpected_loaded_native_library" in result["gaps"]
    else:
        assert result["gaps"] and result["libraries"] == []
