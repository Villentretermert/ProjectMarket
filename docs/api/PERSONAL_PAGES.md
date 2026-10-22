# Personal pages API · PM-016

Implemented in contract revision **1.0.6** (86 schemas / 62 specified operations;
the specification still includes future sharing/update operations). Bot wire version remains 1.0.
Local session and current-account ownership apply to every endpoint. Mutations require
the normal CSRF header and exact Origin. Source access is checked separately.

| Method / path under `/v1/personal-pages` | Result |
|---|---|
| POST root | Create PageWrite at expected version 0 / layout version 1; 201 |
| GET root | Account pages with signed session-bound pagination |
| GET `/{page_id}` | Own title and declarative layout; foreign/deleted 404 |
| GET `/{page_id}/snapshot` | Own layout plus independently authorized current blocks |
| PUT `/{page_id}` | Atomic title/layout replacement with expected version guard |
| DELETE `/{page_id}` | Idempotent 204; never deletes publisher data |

POST requires a stable `Idempotency-Key` of 8–128 ASCII letters, digits, `_` or `-`.
An exact creation replay returns the current page; changed body or a deleted page's
key returns 409. Creation fingerprints remain as tombstones after deletion.
PUT requires layout.template_version = expected_template_version + 1. An identical
replay of the latest saved replacement returns 200; a different stale edit returns
409 template_conflict. Clients must not silently overwrite the later version.

PageWrite contains title, expected_template_version and layout. Layout contains
schema_version, template_version, theme, density and ordered blocks. Each block has
its own unique block_id, source channel/resource reference, content_type, view and
action_ids. See the generated schemas for closed properties and string bounds.

| Content type | Compatible views |
|---|---|
| news | article, compact |
| product | list, card |
| chart | line, bars, table |

Up to 20 active pages/account and 50 blocks/page. News cannot become a numeric chart.
No executable HTML/JS/SQL or data joins are accepted. New or changed references must
match a readable published binding and live record. Retained references may be
reordered, restyled or removed even when source access has disappeared.

Snapshot resolves each source against current membership/grants and publication.
Unavailable results contain only block_id and available=false; available results
include record, current data_revision, slug and currently allowed published actions.
The stored personal layout retains its reference IDs, never a copy of private data.
Removed actions cannot execute through an old personal binding. Request purchase
continues through the original channel's action API and independently checks rights.

Account advisory transaction locks serialize changes; source locks follow the existing
access policy. Undo writes another version. There is no server-side revision history
or public sharing endpoint in PM-016. Personal-page deletion clears title/layout;
account privacy/retention acceptance remains PM-023.
