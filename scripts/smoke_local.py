"""Start installed API from an empty directory, check HTTP, stop only our process."""

import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.smoke_api import check


def main() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("MARKETOB_")
    }
    environment.update(MARKETOB_PORT=str(port), MARKETOB_HOST="127.0.0.1")
    probe = Path(__file__).resolve().parents[1] / "bots/examples/check_gateway.py"
    with tempfile.TemporaryDirectory(prefix="marketob-smoke-") as directory:
        with (Path(directory) / "server.log").open("wb") as log:
            server = subprocess.Popen(
                [sys.executable, "-m", "marketob_api"],
                cwd=directory,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                check(f"http://127.0.0.1:{port}", "not_configured")
                subprocess.run(
                    [sys.executable, str(probe), "--url", f"http://127.0.0.1:{port}"], check=True
                )
            finally:
                if os.name == "nt" and server.poll() is None:
                    # Windows venv redirectors spawn a child: stop our whole process tree.
                    subprocess.run(
                        ["taskkill", "/PID", str(server.pid), "/T", "/F"],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                elif server.poll() is None:
                    server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=10)


if __name__ == "__main__":
    main()
