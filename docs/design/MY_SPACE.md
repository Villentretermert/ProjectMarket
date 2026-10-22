# My Space · PM-016 design

Design prepared before implementation. English product; current density retained.

```text
My Space                      Saved · v4       Undo   Preview   Refresh
Page [My daily space ▼]                        New page
Title [My daily space]         Theme [Blue]    Density [Compact]

Channel [Daily news ▼]         Block [Latest headline ▼]       Add block

News · Article                                        ↑ ↓ Remove
Current headline and full text

Product · Compact list                                ↑ ↓ Remove
Daily essentials                                     Request purchase

Chart · Line                                          ↑ ↓ Remove
Current values with units and accessible data table
```

The first saved personal page opens after login. A page selector accommodates later
template imports without replacing the user's existing page. Pilot engineering bounds:
20 personal pages per account, 50 blocks per page, and 20 Undo steps in the open editor.
Undo is session-local and writes a new version; it never decreases template_version.

Pick a saved readable channel, then one of its published blocks. The personal page
stores references and compatible display choices, not source payloads or permissions.
News: article/compact. Product: list/card. Chart: line/bars/table. Density controls the
supported size/spacing; there is no arbitrary pixel size, code, or data transformation.

Controls save automatically. Title saves after leaving the field or pressing Enter;
selectors/order/add/remove save immediately. Saving/Saved/Not saved are explicit.
Preview hides editing controls; it uses current authorized records. Request purchase
uses the original channel's registered action, current source revision and confirmation.

On uncertain network results, retry the identical replacement. The server accepts
an identical replay of the most recent version; stale different changes return 409.
The conflicting local layout remains visible with Retry/Reload saved choices and no
silent overwrite. New-page creation has an account-scoped idempotency key.

Every snapshot rechecks channel access and published resource bindings. A revoked,
deleted or unpublished source becomes Source unavailable; unrelated blocks still work.
Existing inaccessible references may be rearranged or removed. Adding a new reference
requires a currently readable published block. Private data is never persisted in a
browser cache. Refresh and visibility return revalidate; idle updates are PM-018.

Changing this page never mutates the original B2B layout. Sharing is PM-017 and is
not presented as an available control in this task.
