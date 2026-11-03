# Native notices for pilot 68958f1

4 November 2026 supplement to the [embedded-source snapshot](../68958f1-embedded/README.md).
The [inventory](inventory.json) and [text archive](texts.tar.gz) contain **539 unique
texts**, including all 522 previous texts. Thirty-three additional selections
produce 17 new unique texts after deduplication.

The additions are the version-matched Rust 1.98.1 / 1.99.0 library copyright reports,
upstream license texts shipped beside them, and libffi 3.4.6's license. Copyright
HTML is retained verbatim in the content-addressed text archive. The included
license files provide its adjacent license texts; no HTML rewriting was performed.
The compiler notice collection is conservative, not a statement that all those
components or license alternatives apply to our final binaries.

The four immutable image IDs and 584 installed occurrences / 377 unique installed
components are unchanged. Earlier Alpine gaps, ten source-lock notice gaps and
five absent workspace manifests remain visible. Native evidence is recorded
separately under `native_build_evidence`.

| Wheel | Producer SBOM registry entries | Local dependencies excluding root | ELF Rust version |
| --- | ---: | ---: | --- |
| jsonschema-rs 0.57.1 | 199 | 6 | 1.98.1 |
| pydantic-core 2.50.1 | 99 | 0 | 1.99.0 |
| rpds-py 2026.9.1 | 17 | 0 | 1.99.0 |

All SBOMs declare all-target scope. Two previously missing notices, r-efi 5.2.0
and wit-bindgen-rt 0.39.0, appear in pydantic-core's all-target SBOM.
Their presence does not prove Linux linkage; they remain open source-inventory gaps.

## Verification

```text
python -m scripts.native_notices --verify --output third_party/68958f1-native
```

Offline verification checks the pinned prior inventories, saved evidence hashes,
SBOM identities/checksums/graph coverage, compiler-to-channel associations, cffi
recipe/static-function evidence, notice references and preservation of prior gaps.
It does not re-download wheels or compiler archives, verify attestation signatures,
rebuild software or prove the recorded ELF observations independently.

For a full repeat into a fresh output directory:

```text
python -m scripts.native_notices --fetch --cache .local/native-inputs-new --wheel-cache .local/native-wheels-new --output .local/native-notices-new
```

This additionally verifies five wheel downloads against the previous locked hashes,
their entire native-file sets against installed API evidence, the original SBOM
bytes, fresh ELF parsing, and two official Rust archive hashes before reading their
notices. Downloaded programs are never executed. Exact versions and URLs are in the
[evidence manifest](../native-68958f1/sources.json). The seven small upstream evidence
files are supplied in the repository, so they do not require re-fetching.

Exact producer build features/link maps, nested vendor headers, complete
corresponding-source and relinking materials, Debian source packages and the four
Alpine attribution gaps remain open. This supplement is not a redistribution verdict.
