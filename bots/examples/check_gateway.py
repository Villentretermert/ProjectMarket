"""Connectivity probe for future separate HTTP bots, not a catalog/news bot."""

import argparse
import json
from urllib.request import urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    with urlopen(args.url.rstrip("/") + "/health/live", timeout=5) as response:
        body = json.load(response)
    if body.get("status") != "ok" or body.get("service") != "marketob-api":
        raise SystemExit("Unexpected gateway response")
    print("MarkeTOB gateway is alive; bot endpoints are not implemented yet.")


if __name__ == "__main__":
    main()
