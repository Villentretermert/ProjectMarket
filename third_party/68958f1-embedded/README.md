# Python embedded-source notices for pilot 68958f1

3 November 2026 supplement to the [Alpine snapshot](../68958f1-alpine/README.md).
The four image IDs, 584 installed component occurrences and 377 unique installed
components are unchanged. The [inventory](inventory.json) and [text archive](texts.tar.gz)
contain 522 unique unchanged texts, including all 298 earlier texts.

The additional evidence covers six pinned Python source distributions:
argon2-cffi-bindings 26.1.0, cffi 2.1.1, jsonschema-rs 0.57.1,
psycopg-c 3.3.6, pydantic-core 2.50.1 and rpds-py 2026.9.1.
Five downloaded wheels match the installed API native file hashes exactly.
psycopg-c is built locally from source and was not rebuilt in this collection.

## What the Rust inventory means

The three source Cargo locks contain 490 registry occurrences and 450 unique
name/version/checksum combinations. All 450 crate archives were downloaded
and verified against those checksums. They include development, build and
other-platform inputs. They are recorded separately under
`embedded_source_evidence`; they are **not** added to the installed-component
count and are not claimed to be the exact linked dependency graph.

There are 22 local workspace entries: 17 Cargo manifests are present and checked
by name, version and digest in the corresponding Python sdists. Five entries
from jsonschema's lock have no manifest in its sdist: benchmark-suite,
jsonschema-cli, jsonschema-macros-standalone, jsonschema-rb and jsonschema-wasm.
Their relevance to the Python Linux wheel has not been established.

Dedicated notice files were found in 435 crate archives. Six additional files
from exact VCS commits provide notices for five more crates: codspeed-criterion-compat,
hegeltest-macros, jni-sys-macros, uuid-simd and vsimd. Their repository/commit is
checked against Cargo metadata and `.cargo_vcs_info.json`.
This leaves 10 source-lock entries without a collected notice:

| Package | Version |
| --- | --- |
| anes | 0.1.6 |
| difflib | 0.4.0 |
| r-efi | 5.2.0, 5.3.0, 6.0.0 |
| rustls-platform-verifier-android | 0.1.1 |
| wasip2 | 1.0.1+wasi-0.2.4 |
| winapi-i686-pc-windows-gnu | 0.4.0 |
| winapi-x86_64-pc-windows-gnu | 0.4.0 |
| wit-bindgen-rt | 0.39.0 |

These gaps describe the source-lock inventory, not ten proven Linux runtime
dependencies. No copyright owner or license text was invented to close a gap.

## C libraries and remaining limits

The complete vendored Argon2 license was retained from its pinned sdist.
Its CMake source recipe lists the bundled C implementation. The exact wheel
build environment and source-to-binary reproduction remain open.

The cffi and Argon2 extension dependency lists in the installed API image
contain libc/libpthread and the Linux loader; they do not identify a separate
libffi or libargon2 shared library. The exact libffi source/build version inside
the Linux cffi wheel still requires confirmation. Windows libffi headers in
the cffi sdist were not substituted for that missing Linux evidence.

Rust compiler/runtime attribution, exact wheel build graphs, nested vendor
header review, Debian corresponding sources and complete source delivery remain
open. The four prior Alpine attribution gaps are preserved. Windows/Android
binaries are a separate deferred scope. This is not a redistribution verdict.

## Verification and reproduction

```text
python -m scripts.embedded_notices --verify --output third_party/68958f1-embedded
```

Offline verification checks the unchanged base inventory, uv.lock source/wheel
pins, copied Cargo lock hashes, full registry and workspace entry coverage,
notice associations, retained gaps and every notice archive hash.
It does not re-download sources or re-probe installed binaries.

[Source manifest](../embedded-68958f1/sources.json) and the three byte-preserved
[Cargo locks](../embedded-68958f1/locks) allow a full repeat:

```text
python -m scripts.embedded_notices --fetch --cache .local/embedded-sources-new --output .local/embedded-notices-new --source-archive .local/embedded-source-inputs.tar.gz
```

Use new output and archive paths. This command checks 467 inputs: 6 sdists,
450 crates, 5 wheels and 6 upstream notice files. It verifies the five wheel
native-file hashes against recorded installed API evidence and the source files
against lock/manifests. It executes no build scripts or downloaded code.
The collector rejects bad hashes, changed package/VCS metadata, incomplete
coverage, duplicate or linked selected archive members and native-file mismatches.

The local source-input archive excludes the five binary wheels and contains
462 files, 78,704,698 bytes, SHA-256
`d2a0b53738e4cc472229a3fdb3cbf97b4a737e0213d3d8586123e31ca1e8f297`.
All 462 member hashes were verified after packing. The archive is not uploaded.
Its inputs alone are not a complete corresponding-source delivery or build environment.
