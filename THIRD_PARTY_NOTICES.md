# MarkeTOB third-party notices

Snapshot of the Linux amd64 pilot images tagged `68958f1`, collected on
3 November 2026. API also supplies maintenance and migration services.
Original MarkeTOB code is licensed under [Apache License 2.0](LICENSE).
Third-party software retains its own licenses and copyright notices.

The [inventory](third_party/68958f1-alpine/inventory.json) maps component names, versions,
source-package versions and source paths to SHA-256-addressed notice files.
The [archive](third_party/68958f1-alpine/texts.tar.gz) contains 298 unique, unchanged
license, copyright, patent and NOTICE texts. Shared Debian license texts,
including GPL and LGPL, are included. [Coverage and reading instructions](third_party/68958f1-alpine/README.md)
describe the four remaining package attribution gaps and further review needed.

This collection covers 584 component occurrences across four images,
377 distinct ecosystem/name/version combinations. It includes the modules
recorded in Caddy and gosu binaries, with notice files from matching builders.
Some module-level notices cover source subtrees that are not linked into the
executables. Keeping them does not assert that all those subtrees are shipped.

Psycopg and psycopg-c include LGPL v3 texts. Psycopg-pool has its own license.
Each dependency's recorded text governs its use. Selecting Apache 2.0 for
MarkeTOB does not change dependency terms.

Before distributing complete images, finish the remaining Alpine attribution and bundled-code review
and prepare the applicable corresponding-source materials and replacement/relinking
instructions. This archive supplies notices only and makes no source-code offer.
See the [distribution preparation record](docs/licensing/DISTRIBUTION.md).
The currently running images have not been rebuilt to embed this new sidecar.
