# ADR-0014 · Local delivery and recovery

Status: accepted; Windows/Ubuntu WSL Docker and CI acceptance passed. 2026-10-23.

The owner explicitly deferred Android and authorized local delivery. PM-021's
Web/API/worker subset can proceed independently; native acceptance and task
completion criteria remain visible. No checkpoint is skipped or counted early.

Use the existing Python runtime/worker and PostgreSQL18 image. Web ships in API;
no separate Node runtime. A Compose overlay adds restart/resource bounds and a
non-root Caddy local HTTPS proxy. All host bindings are loopback. CA trust remains
an operator action. A public-domain/cloud deployment is outside this local pilot.

Python orchestrates PostgreSQL custom archives and native/Compose binary streams.
Restore creates a fresh database and uses a single transaction; no --clean,
automatic overwrite, volume removal or automatic cutover. The manifest records
checksum and migration compatibility, without connection credentials. Database
roles, external bot state/config and proxy CA are separate operator backups.

Readiness now checks exact migration names/checksums; migration rejects a newer
database. This prevents an apparently healthy old binary from using a schema it
does not understand. Existing health JSON/status vocabulary remains unchanged.

Rejected alternatives: filesystem copy of a live PostgreSQL volume (not a valid
logical backup), restore-in-place (unnecessary destructive risk), treating a
checksum as restore acceptance, and automatic rollback after writes resume
(would lose acknowledged changes). Downgrade SQL and PITR remain future work.

Recovery copies the source's security state and action history at snapshot time.
An isolated restored instance must be reviewed before cutover; subsequent
revocations/external purchases require reconciliation. No exactly-once claim is
made across independent bot/database disaster recovery.

See [runbook](../setup/LOCAL_DELIVERY.md), [backup](../setup/BACKUP_RESTORE.md)
and [evidence](../task-results/PM-021.md).
