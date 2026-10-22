# Backend acceptance lab

This is a synthetic HTTP test harness, not the Web client. It starts a real API,
maintenance worker and independent bots against a disposable `lab_<uuid>` schema.
It never drops an existing application schema. PostgreSQL itself stays running.
Processes and logs belong to this invocation; only their recorded PIDs are stopped.

From the repository root, with the pinned development environment installed:

```text
uv run --locked python -m scripts.smoke_backend --connection-file .local/postgres-dev/connection.json
uv run --locked python -m scripts.load_backend --connection-file .local/postgres-dev/connection.json
```

The private connection file contains `{"url": "postgresql://..."}` and must not be
committed or printed. Alternatively set `MARKETOB_TEST_DATABASE_URL` in the process
environment and omit `--connection-file`. Use a development database account that
can create/drop schemas. Never point load tests at production. The lab binds the
API to a dynamically chosen loopback port and removes only its generated schema
in `finally`; interrupted machine shutdown may require inspecting leftover `lab_`
schemas before deliberately removing the specific test run.

`smoke_backend` proves:

1. Owner registration, private channel creation, both separate bots and publication.
2. Actual process termination before ACK, after ACK, before result and after result
   acceptance. API restarts between crash and recovery. Each request has one demo
   effect and one accepted result, including the lost-response case.
3. Eight concurrent identical HTTP messages produce one receipt and outbox entry.
4. An injected outbox insert failure rolls back the resource and receipt. Removing
   the test-only database trigger permits retry. The runtime has no fault switch.
5. A stopped/restarted maintenance process handles an aged pending request, which
   the catalog can still reconcile to confirmed. Retention never discards unresolved work.
6. Anonymous private-channel denial and revoked-key replay denial.

`load_backend` defaults to 180 seconds, 100 independent bot identities and 10
authenticated API readers. It schedules 1,000 messages/min independently of
response completion with 16 writer threads. SDK retries are disabled so 429/503
and transport failures remain visible. Ingest quotas stay at 60/min/bot and
1,000/min globally. Only account creation and owner provisioning quotas are raised
inside the disposable lab (1,000 and 10,000 respectively).

The mix is 40% news, 40% products, 20% numeric charts. Record JSON byte sizes,
per-request latency including SDK/HTTP, scheduling lag, status counts, read latency,
schema sizes and actual accepted throughput. After API restart, reconcile every
accepted receipt with its durable receipt and outbox entry, replay a sample and
verify the final source revision of each stream. This proves accepted data survives
process restart, not loss of the database disk. Outbox delivery to foreground
clients is still PM-018. The existing maintenance worker handles retention/timeouts.

CLI options: `--seconds 60..1800`, `--bots 20..100`, `--readers 0..100`,
`--rate 100..1000`, `--report <path>`. Reports contain aggregate synthetic evidence,
never bot keys or user passwords. Private temporary bot configurations are removed
after the fault test. Logs/journals remain ignored under `.local/lab_*` for diagnosis.

Linux CI runs `python scripts/test_postgres.py --backend` against its disposable
Compose test database: the same fault sequence and a smaller 60-second profile
with 20 bots and 2 readers at 1,000 messages/min. Local hardware and Linux CI
timings are distinct measurements. Test results do not establish a 30-minute L2
profile, 100 concurrent UI users, the live-rendering SLO or cloud capacity.
Those checks remain [PM-022](../tasks/PM-022.md) and [PM-018](../tasks/PM-018.md).
