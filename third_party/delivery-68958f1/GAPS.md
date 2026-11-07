# Open coverage items for the source handover

This kit assembles the materials collected for Linux pilot 68958f1. Its checks
establish file integrity and the recorded associations. The coverage state is
partial. Keep this file with the kit and carry these items into any later release.

| ID | Remaining work |
| --- | --- |
| alpine-attribution | Attribution for alpine-baselayout and alpine-baselayout-data 3.7.2-r0, alpine-keys 2.6-r0, alpine-release 3.23.7-r0 |
| native-build-graph | Exact Linux feature/link maps and reproducible builds for the shipped Rust/C wheels; five absent jsonschema workspace manifests |
| nested-vendor-attribution | Review bundled winapi import libraries and generated Android AAR contents, plus nested source headers |
| remaining-source-inputs | The kit contains the collected Debian/Alpine/Python/Rust inputs. A complete offline rebuild also needs the remaining Python sdists, CPython 3.14.9 inputs, Go module/toolchain inputs and other build dependencies. Their full source closures are not supplied by this kit |
| full-rebuild | Validate remaining library replacements and a complete clean rebuild. psycopg-c replacement is the one tested recipe |
| other-platforms | Windows/Android binary-specific notices, sources and device checks remain separate |
| external-release-acceptance | Resolve remaining PM-023 findings and deferred release acceptance, and attach notices/source materials to the actual future distributed image set |

The native inventory retains historical gaps at its collection date. Its
crate-notice supplement supplies the ten subsequently recovered package notices.
Together they contain 546 distinct notice texts. Read both inventories.

The project source snapshot is the installed release commit. Apache-2.0 and
current notices are provided at kit root and in the later tooling snapshot.
These distinct revisions are recorded explicitly in manifest.json.
