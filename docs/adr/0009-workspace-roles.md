# ADR-0009 · Workspace roles and Studio

22 October 2026 · PM-014. User decisions: G03/1–4. Implementation details below are
engineering choices within the authorized local pilot, not additional user answers.

Each user may own one workspace and join other workspaces. Existing organizations
and memberships migrate without changing identifiers. There is one immutable Owner
per workspace; changing/removing that owner is rejected. Account deactivation still
disables that owner's workspace. Ownership transfer/multiple owners are future scope.

| Operation | Owner | Admin | Editor |
|---|---|---|---|
| Read workspace, bot metadata, sources, draft, versions | Yes | Yes | Yes |
| Create/edit page, publish, rollback same audience | Yes | Yes | Yes |
| Public/Selected audience, grants, delete page | Yes | Yes | No |
| Register/revoke bots, bootstrap and operational keys | Yes | Yes | No |
| Add/change/remove Admin/Editor by username | Yes | No | No |
| Remove or demote Owner | No | No | No |

Editors can publish and roll back as requested; changing the audience, including
through a historical rollback, requires a manager. This prevents an editor changing
a selected-user page into a public one by publishing an old definition.

Every resource ID resolves its own workspace and checks current membership. The
optional X-Workspace-ID header selects a workspace for lists and bot creation only;
it is never an authorization claim. Omission preserves legacy personal-owner calls.
Cursors bind account/session, operation and workspace; they cannot cross workspaces.

Operations hold an organization SHARE lock through commit; team mutations take UPDATE.
Thus revocation waits for existing authorized transactions, then blocks later ones.
Source read and pending-request reconciliation use the same membership predicate.
Removing a team member does not remove independent public/explicit read grants.
Lock order: target user where relevant → organization → bot/channel → request.

Alternatives: client-only roles would not protect the API; embedding workspace roles
in long-lived sessions would delay revocation; generic arbitrary permissions would
add unnecessary policy complexity. The explicit three-role matrix keeps checks
auditable and migration small.

Studio shows raw registration/operational secrets only in the issuance dialog; no
browser storage, URLs, logs or page previews retain them. Lost issuance responses
require a fresh registration or key rotation. Expiry banners use server key metadata.

## Superseded ownership rule

D46 / [ADR-0017](0017-personal-data-and-transfer.md) replaces immutable ownership and
owner-account workspace deactivation with explicit transfer and a deletion guard.
All other roles and source authorization remain unchanged.
