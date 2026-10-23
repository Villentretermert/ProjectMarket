# ADR-0012 · Immutable server templates

23 October 2026. Implements PM-017 and the declared G04 assumptions after “Продолжай”.

Use a random 192-bit same-server locator and immutable title/layout snapshot. A
self-contained encrypted code would require key distribution and complicate revocation;
plain executable UI exports are excluded. The locator shares only author-selected title,
appearance and source IDs. A recipient receives no source rights or data through it.

ShareCreate guards the saved template version; both create/import have idempotency keys.
Import bypasses new-reference validation only for this validated server snapshot, so
inaccessible references can be preserved. Every later source read/action still checks
current rights. Default expiry30d, explicit null for no expiry, max20active links/page.
These are announced engineering defaults, not individual answers to G04 questions.

Revoke and page deletion block new imports; existing copies survive. Author deactivation
also blocks locators. In-flight authorized imports may finish before revoke commits.
The share row is locked before source resolution; account locks serialize mutations.
Replaying an already successful import returns its existing copy even after revoke;
deleted copies cannot be recreated with the same key. Revoked metadata retention is PM-023.
