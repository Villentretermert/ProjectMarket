# Working Web client

Start PostgreSQL, migrate and run the API as described in
[LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md), then open
[MarkeTOB](http://127.0.0.1:8000/app/). The same URL works with the API Docker image.
Use the exact allowed origin, including the port. A different localhost hostname
is a different session origin. On a custom port configure `MARKETOB_ALLOWED_ORIGINS`.

Create a local account in the browser, or sign in with the account used to
[provision the two pilot bots](PILOT_BOTS.md). Passwords require 12–128 characters;
usernames use lowercase letters, digits, underscores and hyphens. No cloud account
is required. After login, My Space opens. [Studio](STUDIO.md) now manages real
workspaces/bots/pages/team; the personal editor is connected in PM-016.

Open Channels to see your published pages or paste a shared channel link/slug.
The URL format is `/app/#/channel/<slug>`. Selected-user pages require a session
and read permission; anonymous visitors can read published public pages only.
Data comes from the backend, never from the old design mockup.

Each news/product/chart block has a compatible view selector. This is a temporary
reading preference on a channel; saving personal layout choices belongs to My Space.
Products default to list, news to article in newly provisioned pilot channels.
Charts show axis labels, units and an accessible data table. No external image or
JavaScript from a bot is loaded. Only credential-free HTTPS text links are clickable.

Request purchase opens confirmation: item, quantity one, no payment. The independent
catalog bot supplies the actual outcome. Check status reads the existing request.
If the creation response was lost, recovery repeats the identical request with the
same idempotency key, including after tab reload. The tab stores identifiers and
request input only, never source content, passwords, bot keys or result summaries.
Signing out clears those references. Clearing browser storage loses this recovery
reference; do not submit a new request without checking the existing operation.

Refresh reads current data and rechecks access. Offline or hidden tabs clear source
content; returning/reconnecting loads authorized data again. No service worker or
persistent private-content cache is installed. Foreground update delivery is PM-018.

## Reproduce browser acceptance

```text
cd apps/client
npm ci --ignore-scripts --no-audit --no-fund
npx playwright install chromium
cd ../..
uv run --locked python -m scripts.smoke_web
```

Set `MARKETOB_TEST_DATABASE_URL` privately for an explicitly designated test database.
On this PC use `--connection-file .local/postgres-dev/connection.json` instead. An
isolated `lab_<uuid>` schema is created and dropped; unrelated schemas are untouched.
`MARKETOB_BROWSER_CHANNEL=msedge` uses installed Edge on Windows. Screenshots and
results default to `.local/web-evidence`; `--output` selects another directory.
CI runs Chromium. Node/Playwright are test tools, not Web runtime dependencies.

The suite combines actual HTTP/bot operations with explicitly simulated browser
503/404/offline responses for presentation states. API permission/revocation rules
are independently covered by PostgreSQL integration tests. Mobile viewport checks
are browser checks, not Android device acceptance.

[Studio/команда](STUDIO.md) и [Channels/избранное](FAVORITES.md) работают на том же локальном сервере.
