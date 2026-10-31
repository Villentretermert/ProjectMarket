"""Inventory the binary driver's loaded libraries without connecting to a database.

Exit 0 means complete inventory, not absence of vulnerabilities; exit 2 means a gap.
Output excludes environment values, connection strings and absolute library paths.
"""

import ctypes
import ctypes.util
import hashlib
import importlib.metadata
import json
import os
import platform
import ssl
from pathlib import Path
from typing import Any


def library_kind(name: str) -> str | None:
    for kind in ("libpq", "libssl", "libcrypto"):
        if name.lower().startswith((kind + ".", kind + "-")):
            return kind
    return None


def openssl_version(path: Path) -> str:
    # The caller only passes an absolute, already loaded, wheel-owned library.
    library = ctypes.CDLL(str(path), mode=getattr(os, "RTLD_NOLOAD", ctypes.DEFAULT_MODE))
    version = library.OpenSSL_version
    version.argtypes = [ctypes.c_int]
    version.restype = ctypes.c_char_p
    value = version(0)
    if not isinstance(value, bytes) or not value.startswith(b"OpenSSL "):
        raise ValueError("OpenSSL version unavailable")
    return value.decode("ascii")


def collect_loaded(loaded: list[str], owned: set[Path]) -> dict[str, Any]:
    """Use loader evidence plus wheel ownership; an on-disk copy is not proof of use."""
    libraries: list[dict[str, Any]] = []
    gaps: list[str] = []
    seen: set[Path] = set()
    for name in loaded:
        path = Path(name)
        kind = library_kind(path.name)
        if kind is None:
            continue
        if not path.is_absolute():
            gaps.append(f"unresolved_loaded_path:{kind}")
            continue
        path = path.resolve()
        if path not in owned or path in seen:
            continue
        seen.add(path)
        item: dict[str, Any] = {"name": path.name, "kind": kind, "owner": "psycopg-binary"}
        try:
            with path.open("rb") as stream:
                item["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
            if kind == "libcrypto":
                item["openssl_version"] = openssl_version(path)
        except OSError, AttributeError, ValueError:
            # Loader errors can contain private absolute paths; retain only a stable code.
            gaps.append(f"unreadable_loaded_library:{kind}")
        libraries.append(item)
    for kind in ("libpq", "libssl", "libcrypto"):
        count = sum(item["kind"] == kind for item in libraries)
        if count != 1:
            gaps.append(f"expected_one_loaded_{kind}:found_{count}")
    return {"libraries": sorted(libraries, key=lambda item: item["name"]), "gaps": gaps}


def inspect_runtime() -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "marketob-psycopg-linkage/v1",
        "scope": "Inspection process imports ssl then psycopg; no database or network access",
        "coverage": "Loaded libpq/libssl/libcrypto owned by the psycopg-binary wheel",
        "security_assessment": "not_performed",
        "python": platform.python_version(),
        "platform": platform.system(),
        "machine": platform.machine(),
        "python_ssl": ssl.OPENSSL_VERSION,
        "status": "incomplete",
        "libraries": [],
        "gaps": [],
    }
    try:
        import psycopg

        report.update(
            psycopg=psycopg.__version__,
            implementation=psycopg.pq.__impl__,
            libpq_runtime=psycopg.pq.version(),
            libpq_build=psycopg.pq.__build_version__,
        )
        if psycopg.pq.__impl__ != "binary":
            report["gaps"] = ["unsupported_driver_implementation"]
            return report
        distribution = importlib.metadata.distribution("psycopg-binary")
        files = distribution.files
        if not files:
            report["gaps"] = ["wheel_file_inventory_unavailable"]
            return report
        owned = {Path(str(distribution.locate_file(file))).resolve() for file in files}
        report.update(collect_loaded(ctypes.util.dllist(), owned))
    except ImportError, OSError, ValueError, AttributeError:
        report["gaps"] = ["runtime_inventory_unavailable"]
        return report
    if not report["gaps"]:
        report["status"] = "complete"
    return report


def main() -> int:
    report = inspect_runtime()
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
