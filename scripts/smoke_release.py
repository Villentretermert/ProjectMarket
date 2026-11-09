"""Check the pinned Linux release in a fresh disposable stack with two real bots."""

import argparse
import json
import secrets
import socket
import ssl
import subprocess
import time
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener
from uuid import uuid4

from scripts.delivery_bundle import ROOT, check_recipe
from scripts.docker_lab import DockerLab
from scripts.pilot_bots import provision, publish
from scripts.smoke_ingestion import Http


def configure(lab: DockerLab, images: dict[str, str]) -> str:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = f"https://localhost:{port}"
    lines = ["services:"]
    for service, role in {"api": "api", "migrate": "api", "maintenance": "api", "db": "db"}.items():
        lines.extend([f"  {service}:", "    image: " + json.dumps(images[role])])
        if service == "api":
            origins = json.dumps(json.dumps([lab.origin, origin]))
            lines += ["    environment:", "      MARKETOB_ALLOWED_ORIGINS: " + origins]
    lines += [
        "  proxy:",
        "    image: " + json.dumps(images["proxy"]),
        f'    ports: !override ["127.0.0.1:{port}:8443"]',
    ]
    path = lab.directory / "release.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    lab.command += ["-f", "deploy/compose.local.yaml", "-f", path.as_posix()]
    return origin


def configure_bots(lab: DockerLab, state: Path, image: str) -> None:
    services: dict[str, Any] = {}
    volumes: dict[str, Any] = {}
    for kind in ("catalog", "news"):
        volume = kind + "_state"
        volumes[volume] = {}
        services[kind + "-bot"] = {
            "image": image,
            "env_file": [(state / (kind + ".env")).as_posix()],
            "environment": {
                "MARKETOB_API_URL": "http://api:8000",
                "MARKETOB_ALLOW_CONTAINER_HTTP": "1",
                "MARKETOB_STATE_PATH": "/data/" + kind + ".sqlite3",
            },
            "volumes": [volume + ":/data"],
            "command": ["python", "-m", "marketob_bots." + kind, "--interval", "1"],
            "init": True,
            "read_only": True,
            "tmpfs": ["/tmp"],
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
        }
    path = lab.directory / "bots.json"
    path.write_text(json.dumps({"services": services, "volumes": volumes}), encoding="utf-8")
    lab.command += ["-f", path.as_posix()]


def register(http: Http, name: str, password: str) -> dict[str, str]:
    credentials = {"username": "delivery_" + uuid4().hex[:16], "password": password}
    http.csrf = http.call(
        "POST", "/v1/auth/register", {**credentials, "display_name": name}, expected=201
    )["csrf_token"]
    return credentials


def check_tls(lab: DockerLab, origin: str) -> None:
    # Trust only the disposable proxy CA for this client, never the operating system.
    ca = lab.directory / "root.crt"
    ca.write_bytes(
        lab.run("exec", "-T", "proxy", "cat", "/data/caddy/pki/authorities/local/root.crt")
    )
    jar = CookieJar()
    client = build_opener(
        HTTPSHandler(context=ssl.create_default_context(cafile=str(ca))), HTTPCookieProcessor(jar)
    )
    for attempt in range(20):
        try:
            with client.open(origin + "/health/ready", timeout=10) as response:
                assert json.load(response)["database"] == "ok"
            break
        except URLError:
            if attempt == 19:
                raise
            time.sleep(0.5)
    with client.open(origin + "/app/", timeout=10) as response:
        assert b"MarkeTOB" in response.read()
    request = Request(
        origin + "/v1/auth/register",
        headers={"Origin": origin, "Content-Type": "application/json"},
        data=json.dumps(
            {
                "username": "tls_" + uuid4().hex[:16],
                "password": secrets.token_urlsafe(24),
                "display_name": "Synthetic TLS check",
            }
        ).encode(),
    )
    with client.open(request, timeout=10) as response:
        assert response.status == 201
        account = json.load(response)
    assert any(cookie.secure for cookie in jar)
    with client.open(
        Request(origin + "/v1/auth/session", headers={"Origin": origin}), timeout=10
    ) as response:
        assert json.load(response)["user"] == account["user"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wsl", required=True)
    parser.add_argument("--recipe", default="third_party/delivery-schema-20261109/recipe.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT / ".local"):
        parser.error("Choose a new output directory below .local")
    recipe = check_recipe(recipe_path=args.recipe)
    images = recipe["images"]
    output.mkdir(parents=True)
    lab = DockerLab(args.wsl, recipe["release"])
    evidence: dict[str, Any] = {"images": images, "release_commit": recipe["release_commit"]}
    try:
        tls_origin = configure(lab, images)
        lab.open()
        lab.start("worker")
        lab.run("up", "--detach", "--no-build", "--wait", "proxy")
        check_tls(lab, tls_origin)
        print("PASS: fresh database, migrations, worker, HTTPS and Secure session.", flush=True)
        owner, reader = Http(lab.origin), Http(lab.origin)
        password = secrets.token_urlsafe(24)
        register(owner, "Demo publisher", password)
        credentials = register(reader, "Alex · Demo", password)
        user_id = reader.call("GET", "/v1/auth/session")["user"]["user_id"]
        state = lab.directory / "bots"
        channels = provision(owner, state)
        configure_bots(lab, state, images["bot"])
        for kind in ("catalog", "news"):
            command = [
                "run",
                "--rm",
                "--no-deps",
                kind + "-bot",
                "python",
                "-m",
                "marketob_bots." + kind,
                "--once",
            ]
            lab.run(*command, *(["--offline"] if kind == "news" else []))
        publish(owner, channels)
        for kind, channel in channels.items():
            route = "/v1/channels/" + channel["slug"]
            Http(lab.origin).call("GET", route, expected=404)
            assert len(owner.call("GET", route)["records"]) == (4 if kind == "catalog" else 6)
            owner.call(
                "PUT",
                f"/v1/owner/channels/{channel['channel_id']}/grants/{user_id}",
                {},
                expected=204,
            )
        lab.run("up", "--detach", "--no-build", "catalog-bot")
        running = {}
        for service, role in {
            "api": "api",
            "maintenance": "api",
            "db": "db",
            "proxy": "proxy",
            "catalog-bot": "bot",
        }.items():
            container = lab.run("ps", "-q", service).decode().strip()
            actual = (
                subprocess.check_output(
                    [
                        "wsl",
                        "-d",
                        args.wsl,
                        "--exec",
                        "docker",
                        "inspect",
                        "--format",
                        "{{.Image}}",
                        container,
                    ]
                )
                .decode()
                .strip()
            )
            assert actual == images[role], "Running image differs from recipe"
            running[service] = actual
        print("PASS: pinned images, two HTTP bots, four products and private news.", flush=True)
        subprocess.run(
            ["node", "apps/client/record-demo.mjs"],
            input=json.dumps(
                {
                    "origin": lab.origin,
                    "credentials": credentials,
                    "channels": channels,
                    "output": str(output),
                }
            ),
            text=True,
            encoding="utf-8",
            check=True,
            timeout=300,
        )
        actions = lab.query("SELECT state, count(*) AS n FROM action_requests GROUP BY state")
        assert len(actions) == 1 and actions[0]["n"] == 1 and actions[0]["state"] == "confirmed"
        evidence.update(
            running_images=running,
            tls_ca_verified=True,
            secure_session=True,
            synthetic_data=True,
            database_requests=1,
            database_status="confirmed",
            products=4,
            news_records=6,
            private_channel_check=True,
        )
    finally:
        lab.close()
    evidence["disposable_stack_removed"] = True
    (output / "release.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("PASS: Web request confirmed by Docker Python bot; disposable stack removed.")


if __name__ == "__main__":
    main()
