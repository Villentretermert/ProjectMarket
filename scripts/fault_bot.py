"""Test-only child: terminate at a durable boundary, without production fault switches."""

import argparse
import os
from pathlib import Path
from typing import Any

from marketob_bots.catalog import handle
from marketob_bots.common import configuration
from marketob_bots.state import Journal
from marketob_sdk import BotClient


class FaultClient(BotClient):
    phase: str = ""

    def ack(self, event_id: str) -> dict[str, Any]:
        if self.phase == "before_ack":
            os._exit(91)
        response = super().ack(event_id)
        if self.phase == "after_ack":
            os._exit(91)
        return response

    def result(self, event_id: str, body: dict[str, Any]) -> Any:
        if self.phase == "before_result":
            os._exit(91)
        response = super().result(event_id, body)
        if self.phase == "after_result":
            os._exit(91)
        return response


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument(
        "--phase",
        choices=("before_ack", "after_ack", "before_result", "after_result"),
        required=True,
    )
    args = parser.parse_args()
    config = configuration("catalog", args.env_file)
    client = FaultClient(config.api_url, config.key, attempts=1)
    client.phase = args.phase
    journal = Journal(config.state_path, client.identity()["bot_id"], config.channel_id)
    event = client.events()["items"][0]
    handle(client, journal, event)
    raise AssertionError("The injected termination was not reached")


if __name__ == "__main__":
    main()
