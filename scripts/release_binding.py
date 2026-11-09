"""Bind collected materials to a new release using installed bytes, not tags alone."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from scripts.collect_notices import Collector, verify_bundle
from scripts.delivery_bundle import ROOT, file_hash, json_object, safe_name

BASE = "third_party/68958f1/inventory.json"
NATIVE = "third_party/native-68958f1/sources.json"
MATERIALS = (
    BASE,
    "third_party/68958f1/texts.tar.gz",
    "third_party/68958f1-native/inventory.json",
    "third_party/68958f1-native/texts.tar.gz",
    "third_party/68958f1-crate-notices/inventory.json",
    "third_party/68958f1-crate-notices/texts.tar.gz",
    NATIVE,
    "third_party/debian-68958f1/manifest.json",
    "third_party/alpine-68958f1/sources.json",
    "third_party/delivery-68958f1/recipe.json",
)
PACKAGES = {
    "marketob-api": "apps/api/src/",
    "marketob-contracts": "packages/contracts/src/",
    "marketob-bot-sdk": "packages/bot-sdk/src/",
    "marketob-demo-bots": "bots/pilot/src/",
}
PROBE = r"""
import hashlib,importlib.metadata as m,json,pathlib
own, native = {}, {}
def digest(raw): return hashlib.sha256(raw).hexdigest()
for d in m.distributions():
    name=d.metadata['Name']
    for p in d.files or []:
        f=pathlib.Path(d.locate_file(p))
        if not f.is_file() or '__pycache__' in p.parts: continue
        if p.suffix=='.so': native[str(p)] = digest(f.read_bytes())
        if not name.startswith('marketob-'): continue
        item=own.setdefault(name,{'license':d.metadata.get('License-Expression'),'files':{},'notices':{},'generated_launchers':{}})
        if '..' in p.parts:
            item['generated_launchers'][str(p)]=digest(f.read_bytes())
            continue
        if '.dist-info' in str(p):
            if p.name in ('LICENSE','NOTICE'):
                item['notices'][p.name]=digest(f.read_bytes().replace(b'\r\n',b'\n'))
        else:
            raw=f.read_bytes()
            text=(p.suffix in ('.py','.json','.js','.css','.html','.xml','.sql','.txt','.md')
                  or p.name=='py.typed')
            item['files'][str(p)]={'sha256':digest(raw.replace(b'\r\n',b'\n') if text else raw),
                                  'normalize_lf':text}
print(json.dumps({'own':own,'native':native}))
"""


def images(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = inventory["images"]
    result = {row["role"]: row for row in rows}
    if len(rows) != 4 or set(result) != {"api", "bot", "db", "proxy"}:
        raise ValueError("Expected four unique image roles")
    for row in rows:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", row["id"]):
            raise ValueError("Expected immutable image IDs")
    return result


def compare(before: dict[str, Any], after: dict[str, Any]) -> int:
    old, new = images(before), images(after)
    for role, previous in old.items():
        for key in ("os", "architecture", "components", "shared_notices", "go_source_evidence"):
            if previous.get(key) != new[role].get(key):
                raise ValueError("Collected component/notice evidence changed: " + role + "/" + key)
    if before["gaps"] != after["gaps"]:
        raise ValueError("Installed notice gaps changed")
    return sum(len(row["components"]) for row in new.values())


def check_probes(binding: dict[str, Any], root: Path = ROOT) -> None:
    manifest = json_object((root / NATIVE).read_bytes())
    expected_native = {
        n["file"]["path"]: n["file"]["sha256"] for w in manifest["wheels"] for n in w["native"]
    }
    expected_own = {
        "api": {"marketob-api", "marketob-contracts"},
        "bot": set(PACKAGES) - {"marketob-api"},
    }
    for role in ("api", "bot"):
        probe = binding["probes"][role]
        if probe["image_id"] != binding["images"][role] or set(probe["own"]) != expected_own[role]:
            raise ValueError("Probe image or owned package coverage changed")
        selected = (
            expected_native
            if role == "api"
            else {k: v for k, v in expected_native.items() if k.startswith("rpds/")}
        )
        if not selected or any(probe["native"].get(k) != v for k, v in selected.items()):
            raise ValueError("Native wheel bytes differ from source evidence")
        for package, installed in probe["own"].items():
            launchers = {"../../../bin/marketob-api"} if package == "marketob-api" else set()
            if set(installed["generated_launchers"]) != launchers:
                raise ValueError("Unexpected generated package launcher")
            if installed["license"] != "Apache-2.0" or set(installed["notices"]) != {
                "LICENSE",
                "NOTICE",
            }:
                raise ValueError("Owned license evidence incomplete")
            for name, checksum in installed["notices"].items():
                raw = subprocess.check_output(
                    ["git", "show", binding["release_commit"] + ":" + name], cwd=root
                )
                if hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() != checksum:
                    raise ValueError("Owned license differs from source commit")
            if not installed["files"]:
                raise ValueError("Owned source evidence is empty")
            for name, evidence in installed["files"].items():
                safe_name(name)
                raw = subprocess.check_output(
                    ["git", "show", binding["release_commit"] + ":" + PACKAGES[package] + name],
                    cwd=root,
                )
                if evidence["normalize_lf"]:
                    raw = raw.replace(b"\r\n", b"\n")
                if hashlib.sha256(raw).hexdigest() != evidence["sha256"]:
                    raise ValueError("Installed owned code differs from source commit: " + name)


def verify(path: Path, root: Path = ROOT) -> dict[str, Any]:
    binding = json_object(path.read_bytes())
    if binding["schema"] != "marketob-release-binding/v1" or not re.fullmatch(
        "[0-9a-f]{40}", binding["release_commit"]
    ):
        raise ValueError("Invalid release binding")
    if binding["coverage_state"] != "partial" or not binding["open_items"]:
        raise ValueError("Coverage gaps must remain explicit")
    required = set(MATERIALS) | {
        binding["inventory"],
        str(Path(binding["inventory"]).parent / "texts.tar.gz").replace("\\", "/"),
    }
    if set(binding["bound_files"]) != required:
        raise ValueError("Missing or unexpected material binding")
    for name, checksum in binding["bound_files"].items():
        safe_name(name)
        if file_hash(root / name) != checksum:
            raise ValueError("Bound material changed: " + name)
    current = json_object((root / binding["inventory"]).read_bytes())
    occurrences = compare(json_object((root / BASE).read_bytes()), current)
    if binding["component_occurrences"] != occurrences:
        raise ValueError("Component count differs from inventory")
    if {role: row["id"] for role, row in images(current).items()} != binding["images"]:
        raise ValueError("Inventory images differ from release binding")
    old_recipe = json_object((root / MATERIALS[-1]).read_bytes())
    if binding["open_items"] != old_recipe["open_items"]:
        raise ValueError("Historical open items must not disappear")
    for name in ("68958f1", "68958f1-native", "68958f1-crate-notices"):
        verify_bundle(root / "third_party" / name)
    verify_bundle((root / binding["inventory"]).parent)
    check_probes(binding, root)
    return binding


def collect(inventory: Path, commit: str, wsl: str | None) -> Path:
    relative = inventory.resolve().relative_to(ROOT).as_posix()
    current = json_object(inventory.read_bytes())
    occurrences = compare(json_object((ROOT / BASE).read_bytes()), current)
    collector = Collector(wsl)
    identities = images(current)
    probes = {}
    for role in ("api", "bot"):
        probe = json_object(
            collector.run(identities[role]["id"], "python", "-", stdin=PROBE.encode())
        )
        probes[role] = {"image_id": identities[role]["id"], **probe}
    paths = (*MATERIALS, relative, inventory.parent.relative_to(ROOT).as_posix() + "/texts.tar.gz")
    binding = {
        "schema": "marketob-release-binding/v1",
        "release_commit": commit,
        "images": {role: row["id"] for role, row in identities.items()},
        "inventory": relative,
        "component_occurrences": occurrences,
        "bound_files": {name: file_hash(ROOT / name) for name in paths},
        "probes": probes,
        "coverage_state": "partial",
        "open_items": json_object((ROOT / MATERIALS[-1]).read_bytes())["open_items"],
    }
    check_probes(binding)
    output = inventory.parent / "binding.json"
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(binding, indent=2) + "\n")
    verify(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--wsl")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        value = verify(args.verify)
        print(json.dumps({"result": "PASS", "images": len(value["images"]), "coverage": "partial"}))
    elif args.inventory and args.commit:
        print(collect(args.inventory.resolve(), args.commit, args.wsl).relative_to(ROOT).as_posix())
    else:
        parser.error("Choose --verify or --inventory and --commit")


if __name__ == "__main__":
    main()
