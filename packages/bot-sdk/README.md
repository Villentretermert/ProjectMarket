# Python bot SDK boundary

PM-011 will implement the Python HTTP client here, including authentication,
idempotent ingestion, durable event acknowledgement and result reconciliation.
No SDK is implemented in PM-005. Bots must not import API storage internals.
The normative contract is [PROTOCOL.md](../../docs/api/PROTOCOL.md).
