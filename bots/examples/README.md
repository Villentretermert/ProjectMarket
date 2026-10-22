# Separate bot processes

Catalog/news bots are delivered in PM-011 after authentication, ingestion and action
endpoints. This folder establishes their process boundary, not a fake bot implementation.

`python bots/examples/check_gateway.py` checks only gateway liveness through HTTP.
It requires no platform imports, DB access or credentials. Pass `--url` for another
local port. A healthy gateway does not mean bot registration is implemented.
