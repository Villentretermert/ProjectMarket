# ADR-0015 · Local operations and finite capacity

Status: implemented, acceptance in progress. 2026-10-23, PM-022.

The local pilot has 100 bot identities and 100 simultaneously active clients for
L2. The 10,000 MAU business target does not specify concurrency. Synthetic L2 is
1,000 messages/minute for 30 minutes, followed by a 3,000/minute one-minute burst.
Measure durable HTTP receipt to actual Web DOM revision, successful server
processing time, action availability, retries, errors and reconnect separately.

Use allowlisted JSON HTTP/worker events, not raw access logs or tracebacks. Log
only generated request ID, authenticated bot ID, route template, method, status,
duration and bounded worker counters. Never include bodies, URLs/query strings,
headers, cookies, username, source titles or exception text. Native rotating files
are bounded to five 10 MiB files per process. Docker uses its bounded local log
driver:100MiB for the two-process API container,50MiB for other services. PostgreSQL Docker error statements/details are disabled. Local operators
can read metrics and evaluate alerts through a Python CLI; no public metrics
endpoint, third-party telemetry or outbound alert destination is added.

The frequent worker health subprocess reads the heartbeat using the standard
library only. Full database/API/schema imports occur after the `--health` branch,
avoiding repeated schema compilation every10seconds. Heartbeat freshness and
the Compose command remain unchanged, including rollback compatibility.

Repeated PostgreSQL connection establishment dominated the first 100-browser
warmup. Use lifecycle-owned psycopg pools: primary min2/max32 and auxiliary
min2/max8. Auxiliary capacity serves independently committed quotas and outbox
dispatch, avoiding nested-checkout starvation when all primary connections are
occupied. Both have a 3s wait and max40 waiters. Successful requests commit before
return; exceptions roll back. Borrow checks detect broken connections; pools
close at API shutdown. Initial probes used one API process. After failed native
and Docker repeats, the candidate Docker configuration uses two Uvicorn workers
with16 primary+4 auxiliary connections each:the total remains32+8. Native defaults
to one worker. Settings allow only1–2 workers; multiple workers require stdout,
so independent rotating-file writers cannot corrupt a shared native log.
The candidate still requires a new successful full L2. External replicas need
a separate connection/resource budget.
[Uvicorn process manager](https://uvicorn.dev/deployment/) documents spawn/factory
support; local measurements establish whether this configuration meets our SLO.

The first steady rehearsal also exceeded latency targets. Profiling identified
the Python JSON Schema traversal of chart points as substantial CPU work.
The Message hot path now compiles the identical canonical2020-12 schema through
jsonschema-rs0.57.1, offline with format checks enabled. API/domain logic stays
Python. Canonical fixtures and boundary mutations are compared with the original
validator, which remains for other schemas/reference tests. Snapshot JSON encoding
is reused rather than traversing large chart payloads twice. Mechanism source:
[jsonschema-rs](https://pypi.org/project/jsonschema-rs/).

Finite pilot storage admission is deliberately separate from retention:

- Per bot: 100,000 history rows or 256 MiB of uncompressed JSON, whichever comes
  first. Trigger-maintained counters roll back together with the receipt/snapshot.
  Expiry after 30 days frees capacity. Full storage returns 429/Retry-After60 and
  does not delete unexpired acknowledged data. Exact replay still works.
- Per bot: 10,000 source records including revision tombstones. Existing records
  remain updatable. Physical source deletion/privacy is PM-023.
- Per bot: 1,000 unresolved requests. The bot lock serializes admission across
  channels. ACK alone does not free capacity; a terminal result does. Unknown
  outcomes remain stored and require reconciliation, never silent age deletion.
- Outbox: reject new entries at 20,000 unsequenced or 250,000 total rows. A count
  guard avoids a transaction-wide global counter lock, which would break late
  commit independence. Concurrent in-flight writers can overshoot the threshold;
  these are soft admission thresholds, not a strict SQL row invariant. Rate
  limits and finite API worker concurrency bound the overshoot for this runtime.
- Worker assigns pending delivery order even with no connected clients and
  removes an expired contiguous delivery prefix after one hour, in batches5000.
  A monotonic retention floor forces 410/resync for a cursor behind the retained
  prefix. No delivery ID is reused. Current snapshots and message receipts remain.
- Expired sessions and inactive rate windows/buckets are pruned in bounded batches.

At 100 bots, the history byte budgets allow at most25 GiB of uncompressed raw
JSON, plus indexes, receipts, current records and WAL. This is not a total disk
limit, not a guaranteed 30-day capacity at peak traffic, and not a promise for an
unbounded number of self-registered bots. Operators monitor actual disk reserve
and quota use. Scaling tenant count, storage budgets or full-rate retention needs
a capacity decision and repeat measurement. No backup is deleted automatically.

Sources: [psycopg pool lifecycle and bounds](https://www.psycopg.org/psycopg3/docs/api/pool.html),
[PostgreSQL trigger semantics](https://www.postgresql.org/docs/18/trigger-definition.html),
[Python log rotation](https://docs.python.org/3.14/library/logging.handlers.html).
These justify mechanisms; performance conclusions require the project test report.
