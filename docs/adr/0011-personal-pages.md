# ADR-0011 · Personal layouts and authorized source resolution

Accepted engineering implementation of G03, 22 October 2026.

PersonalPage stores title and a bounded declarative layout; each BlockReference
points at a channel/resource and chooses a compatible view. Payloads and grants
remain at the source. A dedicated snapshot resolves each binding with current rights.
Copying source payloads into layouts was rejected because it makes freshness,
revocation and future template sharing ambiguous.

Account-scoped advisory locks serialize mutations. Optimistic expected versions
detect multiple clients; an identical latest replacement is replayable after a lost
response. New-page POST uses an idempotency key. Last-write-wins was rejected because
it silently loses independent changes. Automatic merge is outside the pilot.

Undo is a bounded in-memory history of 20 successful edits and saves a new version.
20 active pages/account and 50 blocks/page bound work. These are engineering limits,
not additional user answers. Compatible views are enforced by the existing contract.
Density supplies supported size/spacing rather than arbitrary CSS.

Retained inaccessible bindings can be rearranged or removed; adding/changing a
source requires current readable publication and a live typed record. This keeps a
page repairable while preventing fresh private references. Actions are intersected
with current publication and still reauthorized by the original action endpoint.

Deletion clears personal title/layout but retains a creation-key tombstone. Future
sharing must explicitly define revocation on deletion (PM-017). Polling/update delivery
is PM-018; privacy retention/release review is PM-023. Browser drafts never persist
source data. Pending layout edits live only in memory and clear on account changes.
