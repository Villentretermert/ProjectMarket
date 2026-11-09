# Local pilot bots

The [working Web client](WEB.md) reads these real API channels and request statuses.
Open `/app/` and sign in with the same owner account after provisioning.
No Google/Firebase/cloud account is needed. Python 3.14.7 and `uv==0.13.5` are pinned.
First start the backend using [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md).

## Python processes

From the repository root (`uv` may be `.local/uv/Scripts/uv.exe` on this PC):

```text
uv sync --locked
uv run --locked python -m scripts.pilot_bots --username pilot_owner --create-account --offline
uv run --locked python -m marketob_bots.catalog --env-file .local/pilot/catalog.env
uv run --locked python -m marketob_bots.news --env-file .local/pilot/news.env
```

Enter a local account password at the hidden prompt. Omit `--create-account` to
use an existing owner. The preparation publishes two **Selected users** channels;
their URLs and public identifiers are saved in `.local/pilot/channels.json`.
Each bot has its own private `.env` and persistent SQLite journal. Do not commit,
share or print these files. Windows files inherit directory ACLs; use a private
user directory. The scripts request mode 0600 on platforms supporting POSIX modes.

`--offline` seeds synthetic RSS data without internet. Omit it to seed the public
Meduza Russian feed. The continuous news command above reads the real feed every 300 seconds;
add `--offline` to keep synthetic data. Change `MARKETOB_RSS_URL` in `news.env`
for another public HTTPS RSS/Atom feed. Stop each process with Ctrl+C. Restart with
the **same** journal. Never run two writers with separate journals for one bot.

If preparation stopped after both channels were created, use the same account and
directory with `--resume` (without `--create-account`). Partial provisioning is
recorded; inspect owner bot/channel lists before creating replacements. Existing
directories are never silently overwritten. Lost bot keys must be rotated by the owner.

## Separate containers (requires Docker)

Use this alternative for a new pilot directory; do not switch an existing running
bot between host and container journals. The backend remains `compose.yaml`.
The opt-in `compose.bots.yaml` profile adds two independent unprivileged containers.

```text
uv run --locked python -m scripts.pilot_bots --username pilot_owner --create-account --mode docker --offline
docker compose -f compose.yaml -f compose.bots.yaml --profile demo-bots up -d catalog-bot news-bot
```

Preparation writes private configurations, builds both images, seeds the sources
and publishes both channels. Each service uses its own key and journal.

Persistent volumes `marketob_catalog_state` and `marketob_news_state` contain the
bot journals. API origin, internal HTTP opt-in and journal paths are overridden by
the Compose service; neither database password nor URL is passed to the bots.
They have no platform database package. HTTP is only for the local Compose network;
external bots must use a trusted HTTPS API origin and their own key/journal.
The local pilot network is not a production network isolation boundary.

Stop bots with `docker compose -f compose.yaml -f compose.bots.yaml --profile demo-bots stop catalog-bot news-bot`.
Do not delete journal volumes as a way to retry a request. Back up journals together
with deployment state before migrating; see [backup/restore](BACKUP_RESTORE.md).

## Expected behaviour

| Source | Result |
| --- | --- |
| Hand soap / rice | Request purchase → confirmed |
| Paper towels | Request purchase → failed (simulated supplier decline) |
| Milk | Out of stock; API rejects purchase request |
| Public RSS | First five title/date/source-link blocks, in feed order |
| Feed chart | Counts by publication date in the **currently fetched window** |

There are no payments or shipments. Quantity is one. Existing feed data remains
available if fetching/parsing fails. The parser rejects DTD/external entities,
limits XML to 1 MiB and examines at most 100 items; it publishes no full articles.
Missing dates are omitted from the chart. Missing feed slots get explicit placeholders.
The default is `https://meduza.io/rss/all`, following the owner's S06 source choice.
Set `MARKETOB_RSS_URL=https://meduza.io/rss/en/all` for the English edition.
The interface remains English; headlines keep the source language. Known Meduza
and legacy BBC URLs receive explicit publisher attribution; custom feeds receive
the generic source label. Offline fixtures are synthetic and do not fetch this feed.

To change an existing pilot, stop its news process, back up `news.env` and the
SQLite journal, change only `MARKETOB_RSS_URL` in `news.env`, then restart with the
same key/channel/journal. Do not run two publishers for one journal. Existing
`news_1`–`news_5` references in My Space remain valid. Source availability depends
on your network; fetching failure preserves the previous snapshot and retries
at the configured interval. `--once` only publishes one cycle and then exits.
For a source rollback, change the URL while retaining the current journal; do not
restore an older revision journal independently of the matching platform state.

The catalog commits an inbox before ACK and a unique request ledger before result.
On restart it resumes local unfinished events, including accepted results whose
response was lost. Missing local ACKed history is reported as unresolved; no
external operation is reconstructed blindly. The RSS bot persists message IDs,
payloads and revisions before sending; identical data does not republish.

## Verify

```text
uv run --locked pytest -q tests/test_sdk.py tests/test_demo_bots.py
uv run --locked python -m scripts.smoke_bots --mode python
uv run --locked python -m scripts.smoke_bots --mode docker
```

The smoke check creates and deactivates its own synthetic account, verifies both
processes/containers, cross-bot denial, private reads, request outcomes and restart.
It removes only its two temporary credential files and its randomly named Docker
journal volumes. It leaves a secret-free JSON report under `.local/`.
See [SDK quickstart](../../packages/bot-sdk/README.md) for a first custom message
and event/ACK/result integration. Bot creation/management in Telegram is outside scope.
