# MarkeTOB contracts workspace package

Canonical sources and JSON artifacts: [src/contracts](src/contracts/README.md).
Installed Python import remains `contracts`; tests are in [tests](tests/test_protocol.py).
PM-005 relocates PM-004 without changing the 64 schemas or 44 planned operations.

From the repository root:

```sh
uv sync --locked
uv run --locked python -m contracts.build_contract
uv run --locked pytest packages/contracts/tests -q
```

This development dependency is not installed in the API runtime image.
The runtime `/openapi.json` describes only implemented endpoints; this package
describes the intended v1 protocol, including features not implemented yet.
