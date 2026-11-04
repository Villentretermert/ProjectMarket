# Crate notices for pilot 68958f1

Distribute this supplement with the preceding native notice bundle. The 19
references in this inventory point to 12 unique texts. Five already occur in the
base bundle, giving 546 unique texts across both archives. Each archive contains
regular files named by their SHA-256. The inventory identifies the matching
package, source member or immutable upstream URL, and any selected byte range.
[Base bundle](../68958f1-native/README.md) · [Supplement inventory](inventory.json) · [Supplement texts](texts.tar.gz)

Together the two inventories cover package-level notice evidence for all 450
registry entries across the three pinned Cargo locks. The earlier inventory
records the gaps at its collection date. Match this supplement by package name
and version to see the evidence subsequently recovered.

| Packages | Evidence |
| --- | --- |
| r-efi 5.2.0, 5.3.0, 6.0.0 | Complete AUTHORS files containing copyright and license terms |
| winapi-i686-pc-windows-gnu and winapi-x86_64-pc-windows-gnu 0.4.0 | Complete copyright and license headers in build.rs and src/lib.rs for each crate |
| anes 0.1.6 | Packaged README license section and both license files at the crate's recorded commit |
| wasip2 1.0.1+wasi-0.2.4 and wit-bindgen-rt 0.39.0 | All three root license texts from each recorded commit, including the LLVM exception |
| difflib 0.4.0 | MIT license from the tree matching the original manifest and six packaged Rust files |
| rustls-platform-verifier-android 0.1.1 | Both root license files from the release commit matching the original Android crate manifest and its Rust source |

The winapi headers cover the identified Rust files. Attribution of bundled
import libraries and the generated Android AAR requires separate review.
Exact binary linkage, the five missing workspace manifests and Alpine or Debian
materials are separate parts of release preparation.

## Reproduce

Verify the supplement, its base, source associations and notice hashes offline.

```text
python -m scripts.crate_notices
```

Repeat the comparisons from a fresh cache with the original crate and upstream
bytes. This checks 10 locked crates, 11 upstream license files and nine files
used for the two source tree matches. Cached runs can omit `--fetch`.

```text
python -m scripts.crate_notices --cache .local/crate-replay --fetch
```

Prepare one archive containing all six pinned Python source distributions, 450
crates and 26 upstream files used in the base and supplement. This includes the
original manifest and Rust sources used to match repositories without embedded
commit metadata. Use a new output filename. The command verifies all inputs
before writing them as regular files. The resulting archive supplies source
inputs for the Python/Rust review. Rebuilding a release also requires its build
environment and platform sources.

```text
python -m scripts.crate_notices --cache .local/crate-replay --fetch --source-archive .local/embedded-source-inputs.tar.gz
```
