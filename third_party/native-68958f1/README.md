# Native build evidence for pilot 68958f1

The [manifest](sources.json) binds seven byte-preserved public upstream evidence
files in [evidence.tar.gz](evidence.tar.gz): three wheel SBOMs, two official Rust
channel manifests, the cffi release workflow and libffi's license. SHA-256 and,
where available, Git blob IDs are checked. Public producer CI paths and authors
are retained only in the original upstream SBOMs; the derived graph uses package IDs.

Five wheel native-file sets match the recorded installed API image hashes.
Collection rechecks those wheel bytes and extracts ELF comments, Rust compiler
commit markers and the defined `cffistatic_ffi_call` function. Offline CI checks
the saved evidence and associations; it does not inspect a running container.

The three SBOMs declare **all targets**. Their 315 registry occurrences match
the previous Cargo/source inventory. Six additional local dependency entries
and three roots have matching manifests in the sdists. This is producer-declared
dependency evidence, not an exact Linux link map or proof of all compiled features.

Rust 1.98.1 and 1.99.0 official Linux compiler distributions provide version-matched
library copyright reports and license texts. They are downloaded as data and never
installed or executed. The copyright reports conservatively include components
that may not be linked into our wheels; the compiler itself is not added to the
application's installed inventory. These are binary distributions, not a
corresponding-source archive.

cffi 2.1.1's pinned release workflow downloads libffi 3.4.6, disables shared builds
and renames `ffi_call`. The installed matching wheel defines that renamed function.
This corroborates the release recipe; it is not cryptographically verified build
provenance or a byte-for-byte rebuild.

See the [combined notices](../68958f1-native/README.md) and
[engineering report](../../docs/task-results/PM-023-native-provenance-20261104.md).
