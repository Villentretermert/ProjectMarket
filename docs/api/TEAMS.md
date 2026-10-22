# Workspace API · PM-014

Contract revision 1.0.4, unchanged bot wire schema 1.0. The role matrix and lock
ordering are specified in [ADR-0009](../adr/0009-workspace-roles.md).

| Method / route | Behavior |
|---|---|
| GET /v1/workspaces | Paginated active workspaces of current session; org_id, name, role |
| GET /v1/workspaces/{org_id}/members | Paginated public account profiles plus role; current members only |
| PUT /v1/workspaces/{org_id}/members | Owner upserts `{username, role}`; exact registered username, role admin/editor |
| DELETE /v1/workspaces/{org_id}/members/{user_id} | Owner removes membership; idempotent, immutable owner protected |
| GET /v1/owner/channels/{channel_id}/audience | Owner/Admin reads explicitly granted public account profiles |

All routes require a session. Mutations require exact allowed Origin and the session's
X-CSRF-Token. Lists have limit 1–100, signed 60-second cursors and nullable next_cursor.
The membership/audience cursor cannot be reused across sessions, operations or workspaces.
No key, password, email or private account data is returned.

`X-Workspace-ID` optionally selects a workspace for GET/POST /v1/bots,
GET /v1/owner/channels and GET /v1/users/by-username/{username}. Omission retains the
caller's personal owner workspace. Resource routes resolve the workspace from the
resource ID and verify membership independently. A header never grants authorization.
The UI additionally verifies the resource belongs to the selected workspace.

Unknown/nonmember workspace/resource: generic 404. Current member with insufficient
role: 403. Attempt to remove/demote the single Owner: 409 owner_protected. Invalid
role or extra input: 422. Unknown registered username is 404 after owner authorization.

Editors read bot metadata and source inventories, create Selected-user drafts,
edit allowed blocks/actions and publish/rollback. Audience changes, read grants,
page deletion and all credential/bot mutations require Owner/Admin. Team mutation
requires Owner. There is no ownership-transfer endpoint.

Membership removal commits before returning. Existing authorized transactions can
finish before that commit; subsequent requests recheck the current membership.
Private source reads and pending requests also honor memberships. Removal preserves
independent public/read grants; otherwise unACKed requests cancel and ACKed requests
remain unknown for reconciliation. Account deactivation continues to disable its
owned workspace and remove its memberships.

Migration 006 only expands the existing role constraint and adds a sequence/index
for paginated member lookup; old owner identities and existing bot keys are preserved.
