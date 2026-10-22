# MarkeTOB contract 1.0

PM-004 specification, not a running service. Normative rules: [PROTOCOL](../../../../docs/api/PROTOCOL.md); integration walkthrough: [QUICKSTART](../../../../docs/api/QUICKSTART.md).

```powershell
uv sync --locked
uv run --locked python -m contracts.build_contract
uv run --locked pytest packages/contracts/tests -q
```

`build_contract.py` is the source for `openapi.json` and `schemas.json`. The test suite detects generated-file drift, validates OpenAPI and schema examples, and executes failure/recovery scenarios in `reference_model.py`. The model is single-process/in-memory, with synthetic identities: it is not an authentication, transaction or persistence implementation. Replay these scenarios against the future HTTP/PostgreSQL backend in PM-007–012.

`examples/cases.json` labels valid/invalid instances. Select `$defs/<schema>` in the JSON Schema bundle. Object fields are closed and documented. Format checks are enabled explicitly. Schema bounds alone cannot enforce ownership, reference integrity or transaction ordering; those obligations are documented in the protocol and must be implemented server-side.
