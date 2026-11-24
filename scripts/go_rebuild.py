"""Rebuild the delivered Caddy/gosu from verified sources in offline containers.

The pinned Go image must already be present. This rebuild does not bootstrap
the compiler or install the results into the pilot. All orchestration is stdlib.
"""

import argparse
import io
import json
import re
import subprocess
import tarfile
import uuid
from pathlib import Path
from typing import Any

from scripts import go_sources as sources

ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN = (
    "golang:1.26.10-alpine3.23@sha256:"
    "0525c952defebc693cdaf62cdf43afa32be5a7f377e99260642ea19c240c708e"
)
RECEIPT = ROOT / "docs/task-results/assets/PM-023/go-20261124/receipt.json"
OFFLINE_ENV = {
    "GOPROXY": "off",
    "GOSUMDB": "off",
    "GOWORK": "off",
    "GOENV": "",  # go env reports no configuration file when GOENV=off.
    "GOCACHE": "/work/buildcache",
    "GOMODCACHE": "/work/mod",
    "GOTMPDIR": "/work/tmp",
    "GOPATH": "/work/gopath",
    "GOFLAGS": "",
}
BUILD = """set -eu
test -z "$(ls -A /work)"
test ! -e /work/buildcache
test ! -e /work/mod
printf 'empty-work-volume\\n' > /output/initial-state.txt
ls /sys/class/net > /output/network-links.txt
test "$(cat /output/network-links.txt)" = lo
tar -xf /inputs.tar -C /work
mkdir /work/tmp
export GOPATH=/work/gopath GOMODCACHE=/work/mod GOCACHE=/work/buildcache
export GOTMPDIR=/work/tmp
export GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local GOWORK=off GOENV=off GOTELEMETRY=off
export CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOAMD64=v1 GOMAXPROCS=2 GOFLAGS=
cp /usr/local/go/VERSION /output/toolchain-VERSION
sha256sum /usr/local/go/bin/go > /output/toolchain-sha256.txt
go env -json GOVERSION GOOS GOARCH CGO_ENABLED GOTOOLCHAIN > /output/toolchain-env.json
go env -json GOPROXY GOSUMDB GOWORK GOENV GOCACHE GOMODCACHE \\
    GOTMPDIR GOPATH GOFLAGS > /output/offline-env.json
for role in db proxy; do
  cd /work/src/$role
  go mod verify > /output/$role-verify.txt
  go build -p=2 -mod=readonly -trimpath -o /output/$role .
  go version -m /output/$role > /output/$role-build-info.txt
  cp go.mod /output/$role-go.mod
  cp go.sum /output/$role-go.sum
done
cd /work/probe
go build -p=2 -mod=readonly -trimpath -o /output/tls-probe .
"""
CADDYFILE = """{
    admin off
    persist_config off
    skip_install_trust
    auto_https disable_redirects
    # Present the localhost certificate to the negative IP-name test (no SNI).
    default_sni localhost
}
https://localhost:8443 {
    tls internal
    respond /rebuild "offline-rebuild-ok" 200
}
"""
CADDY_SMOKE = """set -eu
export XDG_DATA_HOME=/tmp/data XDG_CONFIG_HOME=/tmp/config HOME=/tmp
/output/proxy run --config /Caddyfile --adapter caddyfile > /tmp/caddy.log 2>&1 &
server=$!
trap 'kill "$server" 2>/dev/null || true' EXIT
if ! /output/tls-probe /tmp/data/caddy/pki/authorities/local/root.crt; then
  cat /tmp/caddy.log >&2
  exit 1
fi
"""
GOSU_SMOKE = """set -eu
test "$(/output/db nobody id -u)" = "$(id -u nobody)"
test "$(/output/db 12345:12346 id -u)" = 12345
test "$(/output/db 12345:12346 id -g)" = 12346
test "$(/output/db --version)" = '1.19 (go1.26.10 on linux/amd64; gc)'
printf '{"result":"PASS","nobody":true,"explicit_uid_gid":true,"version":true}\\n'
"""


def write_inputs(kit: Path, plan: dict[str, Any], output: Path) -> dict[str, Any]:
    """Write a deterministic download cache, never a cached compiler output."""
    seen: set[str] = set()
    with output.open("xb") as dest, tarfile.open(fileobj=dest, mode="w") as archive:

        def add(name: str, raw: bytes) -> None:
            sources.safe_path(name)
            if name in seen:
                raise ValueError("Duplicate prepared input")
            seen.add(name)
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(raw), 0o644
            archive.addfile(member, io.BytesIO(raw))

        for row in plan["modules"]:
            sources.flat_name(row["filename"])
            prefix = "mod/cache/download/" + sources.escaped(row["name"])
            prefix += "/@v/" + sources.escaped(row["version"])
            if row["kind"] not in ("mod", "zip"):
                raise ValueError("Unsupported Go input kind")
            add(prefix + "." + row["kind"], (kit / row["filename"]).read_bytes())
            if row["kind"] == "zip":
                add(prefix + ".ziphash", row["h1"].encode())
        for role in ("db", "proxy"):
            names = ["go.mod", "go.sum", "main.go"]
            if role == "db":
                names += ["version.go", "setup-user.go", "LICENSE"]
            for name in names:
                add("src/" + role + "/" + name, (kit / (role + "-" + name)).read_bytes())
        # This probe is our own disposable stdlib client, not a new product dependency.
        raw = (ROOT / "deploy/go-rebuild/tls_probe.go").read_bytes().replace(b"\r\n", b"\n")
        add("probe/main.go", raw)
        add("probe/go.mod", b"module marketob.local/offlineprobe\n\ngo 1.26.10\n")
    return {"members": len(seen), **sources.file_spec(output)}


def normalized_build_info(raw: bytes) -> list[str]:
    lines = raw.decode().splitlines()
    if not lines or lines[0].split()[-1] != "go1.26.10":
        raise ValueError("Unexpected Go build-info version")
    # Only the inspection pathname changes, not the version or metadata lines.
    return ["go1.26.10", *lines[1:]]


def validate_build(kit: Path, output: Path) -> dict[str, Any]:
    runtime = sources.object_json((kit / "runtime.json").read_bytes())
    if (output / "initial-state.txt").read_bytes() != b"empty-work-volume\n":
        raise ValueError("Initial empty cache observation missing")
    if (output / "network-links.txt").read_bytes() != b"lo\n":
        raise ValueError("Unexpected network interface in offline build")
    if sources.object_json((output / "offline-env.json").read_bytes()) != OFFLINE_ENV:
        raise ValueError("Offline cache/environment mismatch")
    if (output / "toolchain-VERSION").read_bytes() != (kit / "go-VERSION").read_bytes():
        raise ValueError("Toolchain source version differs")
    env = sources.object_json((output / "toolchain-env.json").read_bytes())
    if env != sources.object_json((kit / "proxy-go-env.json").read_bytes()):
        raise ValueError("Toolchain environment differs")
    compiler_sha = (output / "toolchain-sha256.txt").read_text().split()[0]
    if not re.fullmatch(r"[0-9a-f]{64}", compiler_sha):
        raise ValueError("Missing compiler binary hash")
    binaries = {}
    for role in ("db", "proxy"):
        spec = sources.file_spec(output / role)
        if spec["sha256"] != runtime[role]["binary_sha256"]:
            raise ValueError("Rebuilt binary differs from installed " + role)
        if normalized_build_info((output / f"{role}-build-info.txt").read_bytes()) != (
            normalized_build_info((kit / f"{role}-build-info.txt").read_bytes())
        ):
            raise ValueError("Rebuilt module/build metadata differs")
        for name in ("go.mod", "go.sum"):
            if (output / f"{role}-{name}").read_bytes() != (kit / f"{role}-{name}").read_bytes():
                raise ValueError("Build rewrote locked module inputs")
        if (output / f"{role}-verify.txt").read_text().strip() != "all modules verified":
            raise ValueError("Go cache verification missing")
        binaries[role] = {**spec, "image_id": runtime[role]["image_id"], "byte_identical": True}
    return {
        "binaries": binaries,
        "compiler_sha256": compiler_sha,
        "go_environment": env,
        "offline_environment": OFFLINE_ENV,
        "observed_network_interfaces": ["lo"],
    }


class Docker:
    def __init__(self, wsl: str | None):
        self.wsl = wsl
        self.prefix = ["wsl", "-d", wsl, "--exec", "docker"] if wsl else ["docker"]

    def run(self, *args: str, timeout: int = 120) -> bytes:
        return subprocess.check_output(self.prefix + list(args), timeout=timeout)

    def mount(self, path: Path, target: str, readonly: bool = True) -> list[str]:
        absolute = str(path.resolve())
        if self.wsl:
            absolute = subprocess.check_output(
                ["wsl", "-d", self.wsl, "--exec", "wslpath", "-a", absolute],
                timeout=30,
                encoding="utf-8",
            ).strip()
        if "," in absolute or "\n" in absolute:
            raise ValueError("Unsupported Docker mount path")
        return [
            "--mount",
            f"type=bind,src={absolute},dst={target}" + (",readonly" if readonly else ""),
        ]

    def container(
        self, name: str, options: list[str], script: str, log: Path, timeout: int = 120
    ) -> bytes:
        command = self.prefix + [
            "run",
            "--rm",
            "--pull",
            "never",
            "--platform",
            "linux/amd64",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--cpus",
            "2",
            "--memory",
            "3g",
            "--pids-limit",
            "256",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,mode=1777,size=64m",
            *options,
            "--entrypoint",
            "sh",
            TOOLCHAIN,
            "-c",
            script,
        ]
        try:
            with log.open("wb") as stream:
                result = subprocess.run(
                    command, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout
                )
            if result.returncode:
                raise RuntimeError("Offline container failed; see " + log.name)
            return log.read_bytes()
        finally:
            # Names are generated per invocation, never selected from running user services.
            subprocess.run(self.prefix + ["rm", "--force", name], capture_output=True, timeout=30)


def runtime_checks(output: Path) -> dict[str, Any]:
    expected = {
        "gosu": {"result": "PASS", "nobody": True, "explicit_uid_gid": True, "version": True},
        "https": {
            "result": "PASS",
            "https": True,
            "http2": True,
            "untrusted_ca_rejected": True,
            "wrong_hostname_rejected": True,
        },
    }
    # Docker may emit host warnings; retain only the probe's single complete JSON result.
    for name, wanted in expected.items():
        lines = (output / (name + ".log")).read_text(encoding="utf-8").splitlines()
        results = [sources.object_json(line.encode()) for line in lines if line.startswith("{")]
        if results != [wanted]:
            raise ValueError("Missing or incomplete runtime probe")
    return expected


def run(kit: Path, output: Path, wsl: str | None) -> dict[str, Any]:
    receipt = sources.object_json(RECEIPT.read_bytes())
    expected = receipt["manifest_sha256"]
    sources.verify(kit, expected)
    plan = sources.object_json((kit / "source-plan.json").read_bytes())
    for role in ("db", "proxy"):
        if (
            not (kit / ("Dockerfile." + role))
            .read_text()
            .startswith("FROM " + TOOLCHAIN + " AS builder")
        ):
            raise ValueError("Toolchain differs from original build recipe")
    output.mkdir(parents=True, exist_ok=False)
    docker = Docker(wsl)
    volume = "marketob-go-build-" + uuid.uuid4().hex
    created = False
    try:
        identity = json.loads(docker.run("image", "inspect", "--format", "{{json .}}", TOOLCHAIN))
        if (identity["Os"], identity["Architecture"]) != ("linux", "amd64"):
            raise ValueError("Expected Linux amd64 toolchain image")
        if not any(d.endswith("@" + TOOLCHAIN.split("@")[1]) for d in identity["RepoDigests"]):
            raise ValueError("Toolchain digest mismatch")
        tar = output / "inputs.tar"
        prepared = write_inputs(kit, plan, tar)
        binaries = output / "binaries"
        binaries.mkdir()
        docker.run("volume", "create", volume)
        created = True
        options = ["--mount", f"type=volume,src={volume},dst=/work"]
        options += docker.mount(tar, "/inputs.tar") + docker.mount(binaries, "/output", False)
        docker.container(volume + "-compile", options, BUILD, output / "build.log", timeout=1200)
        build = validate_build(kit, binaries)
        caddyfile = output / "Caddyfile"
        caddyfile.write_text(CADDYFILE, encoding="utf-8", newline="\n")
        docker.container(
            volume + "-gosu",
            docker.mount(binaries, "/output") + ["--cap-add", "SETUID", "--cap-add", "SETGID"],
            GOSU_SMOKE,
            output / "gosu.log",
        )
        docker.container(
            volume + "-https",
            docker.mount(binaries, "/output")
            + docker.mount(caddyfile, "/Caddyfile")
            + ["--user", "65534:65534"],
            CADDY_SMOKE,
            output / "https.log",
        )
        checks = runtime_checks(output)
        result = {
            "result": "PASS",
            "source_manifest_sha256": expected,
            "toolchain": {"reference": TOOLCHAIN, "image_id": identity["Id"]},
            "prepared_inputs": prepared,
            "network": "none",
            "initial_work_volume": "empty",
            "runtime_checks": checks,
            **build,
            "limitations": [
                "compiler-bootstrap",
                "full-image-rebuild",
                "other-native-source-gaps",
                "release-acceptance",
            ],
        }
        (output / "result.json").write_bytes(sources.json_bytes(result))
        return result
    except Exception:
        (output / "INCOMPLETE.txt").write_text("Rebuild incomplete; not an accepted delivery.\n")
        raise
    finally:
        if created:
            docker.run("volume", "rm", volume)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wsl")
    args = parser.parse_args()
    resolved = args.output.resolve()
    if not resolved.is_relative_to(ROOT / ".local") or resolved == ROOT / ".local":
        parser.error("Output must be a new directory below repository .local")
    print(json.dumps(run(args.kit, args.output, args.wsl), indent=2))


if __name__ == "__main__":
    main()
