# B2B Studio

Open `/app/`, create/sign in to a local account, then choose **Studio**. No terminal
is needed for workspace, bot registration, layout or team management. Your bot itself
is an independent HTTP service; its implementation/deployment stays outside Studio.

1. Create your workspace and register a bot. Store the single-use registration
   credential from the issuance dialog; it expires in 15 minutes. Closing clears it.
2. Give the credential to your service. It exchanges it with
   `POST /v1/bot-registrations/exchange`, Authorization Bearer, JSON `{}`. Store the
   returned operational key in that service's private environment. The
   [Python SDK](../../packages/bot-sdk/README.md) implements this exchange.
3. Create a page and copy its channel ID into your bot configuration. Newly created
   pages use Selected users. Send data using [the API protocol](../api/PROTOCOL.md),
   then Refresh in Studio to see source records.
4. Add news/product/chart sources, select compatible views, order blocks and enable
   Request purchase for chosen products. Save draft, Preview saved draft, then Publish.
   Publishing is disabled while unsaved edits exist. A version conflict keeps your
   local edits and shows an error; refresh only when ready to discard them.
5. Owner/Admin can select Public or grant read access by exact registered username.
   Save and publish audience changes. Copy page link shares a location, never rights.
6. Version history restores a previously published definition as a new published
   version. Source data stays current. The confirmation warns that unsaved edits
   will be discarded.

**Keys:** inventory contains prefix/scopes/expiry only. A reminder appears within
seven days and after expiry. Rotation immediately revokes the chosen old key; save
the new key before closing and update your bot. Revoke key stops that credential;
Revoke bot stops all its credentials and makes its channels unavailable. Bot
revocation cannot be undone. No secret is stored in browser storage or page layouts.
If an issuance response is lost, renew registration or issue/rotate a new key.

**Team:** Owner adds an existing account by username as Editor or Admin. Owner alone
changes/removes team members. Admin manages bots, keys, audience and pages. Editor
can design, publish and roll back within the current audience, but cannot change
publicity or read grants. The pilot has one current Owner. A team member can belong
to multiple workspaces; select the workspace before working.

Removing a member takes effect on later server operations immediately after commit.
Machine keys belong to the workspace's bot, not to the member who issued them;
rotate/revoke a key separately if its holder should no longer use it.
Independently granted read access remains separate. Foreground consumer screens
detect remote revocation through live updates; Studio uses Refresh. Hidden/offline
content is cleared and revalidated when returning. The backend always checks current rights.

The **Delete page** confirmation unpublishes and retains historical records; it does
not erase source/history data. It cannot be reactivated through Studio in this pilot.

**Transfer ownership:** open Team, choose an existing Admin and enter your current
password. Review the recipient before confirming. That Admin must not already own
a workspace. You become Admin; the new Owner controls the team. Existing bot keys
continue to work and can be rotated by the new Owner. After a lost response,
Refresh to inspect actual roles. Account deletion is blocked until ownership is transferred.

**Data & privacy:** open the link next to Sign out. Download JSON exports your
personal setup and request metadata. Review deletion requires current password and
`DELETE`; the final dialog explains retained requests, username/ID and external
copies. See [Privacy API](../api/PRIVACY.md) for the exact technical policy.
