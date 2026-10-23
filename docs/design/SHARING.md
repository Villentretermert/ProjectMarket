# Share / Import · PM-017 design before implementation

```text
My Space     Share   Import template   Undo   Preview
Share personal page
Title, appearance and source references only. Source access is separate.
Expires [30 days / 7 days / Never]     Create link
Link [same server /app/#/import/CODE]  Copy link / Copy code / Revoke

Import template
Link or code [                  ]     Preview template
Title (copy), theme, density, ordered block types
Available / Source unavailable        Import as new page
```

Sources contain no payload in the shared template. Preview requires login and marks
each source using the recipient's current rights. Unavailable references remain as
placeholders; importing never grants access. Imports get version 1 and are independent.
Codes contain 192 random bits and are server locators, not encrypted offline layouts.
Links use a URL fragment; no code is sent in URL paths or logs. An import link survives
sign-in/registration. Same-origin only; loopback links require the same server address
to be reachable by the recipient (no tunnel or cloud is provisioned here).

Creation/import use idempotency keys and show an explicit retry on a lost response.
Share creation checks the saved template version. Default expiry 30 days, optional
7 days/no expiry. List/revoke only own active shares. Up to 20 active shares per page.
Deleting the original page revokes its links; old imports are unchanged. Author changes
do not update a previously issued snapshot. These bounds are pilot engineering choices.
