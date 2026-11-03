# Alpine source notices for pilot 68958f1

This is the 3 November 2026 supplement to the [original snapshot](../68958f1/README.md).
The image IDs and 584 component occurrences are unchanged. There are still
377 distinct ecosystem/name/version combinations.

[inventory.json](inventory.json) and [texts.tar.gz](texts.tar.gz) now contain
298 unique text files. Source notices or exact copyright/license headers were
found for 28 of the 32 Alpine binary packages. The four entries below retain
their gaps. This is evidence collection, with no complete compliance verdict.

| Package | Declared license | Remaining evidence gap |
| --- | --- | --- |
| alpine-baselayout 3.7.2-r0 | GPL-2.0-only | No dedicated package copyright/license notice in the pinned directory |
| alpine-baselayout-data 3.7.2-r0 | GPL-2.0-only | Same source package |
| alpine-keys 2.6-r0 | MIT | Declaration and public keys, no dedicated attribution/license text |
| alpine-release 3.23.7-r0 | MIT | Generated release data, no dedicated attribution/license text |

No copyright holder was inferred from a package maintainer. Standard GPL/MPL
texts are retained in the base collection. A verbatim MIT template from SPDX
is recorded as standard terms, with its placeholders intact. Actual attribution
comes from source notices and headers. The template does not close these gaps.

The 42 notice selections cover complete upstream notice files and selected
source headers with exact byte ranges. Module/source-package notices can include
build and test subtrees. The presence of their texts does not assert that those
subtrees are included in the binary. One empty `zstd/build/LICENSE` file is
explicitly excluded as evidence; root LICENSE and COPYING are preserved.

## Verification and reading

```text
python -m scripts.alpine_notices --verify --output third_party/68958f1-alpine
```

This offline command checks the base inventory hash, image/source associations,
retained gaps, text hashes and archive references. Extract `texts.tar.gz` to a
new directory with an archive viewer, then look up `texts/<SHA-256>.txt` using
the inventory. Only regular files with content-addressed names are stored.

## Repeating the source collection

[sources.json](../alpine-68958f1/sources.json) records all 20 aports revisions,
167 files verified against Git blob IDs, and 19 external inputs. All 152 entries
from the recipes' SHA-512 tables are checked. The 14 other aports files include
installation scripts; the recipes themselves account for 20 files.
With the standard MIT template the input set has 187 files.

```text
python -m scripts.alpine_notices --fetch --cache .local/alpine-sources-new --output .local/alpine-notices-new --source-archive .local/alpine-source-inputs.tar.gz
```

Use a new output directory and source-archive filename. Omit `--fetch` to use
an already populated cache offline. The collector never executes APKBUILD,
package scripts, patches or downloaded code. It rejects mismatched checksums,
versions, missing inputs, non-regular notice members and escaping paths.

The locally produced source-input archive has SHA-256
`b6afc1f597c2f0e173e08ecfd34387da6ce46048289c399e8faff45161ecc21b`
and contains 187 files, 80,916,989 compressed bytes. All member hashes were
verified after creation. It retains original file bytes as regular data files,
with mode 0644. Rebuilding package executables, restoring executable modes when
needed and assembling the build environment remain separate work. The archive
has not been uploaded or offered as complete corresponding source.

This supplement does not complete the Debian, embedded Rust/C, native Windows
or Android source/attribution work. See [distribution preparation](../../docs/licensing/DISTRIBUTION.md).
