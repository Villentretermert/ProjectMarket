# Go source supplement · schema-20261109

Recorded Caddy/gosu build inputs, not a full reproducible-build attestation.
The runtime images and historical delivery archives remain unchanged.

The kit includes every entry in the observed db/proxy go.sum files: 221 module
ZIP inputs and 370 go.mod inputs (591 records, with identical bytes deduplicated).
These include build/test/transitive inputs beyond the 162 modules present in
the two binaries. A go.sum entry does not establish runtime reachability.
Go 1.26.10 and gosu 1.19 source tarballs are also included. Exact build metadata,
go.mod/go.sum, Caddy main, gosu Go files, upstream license texts and the installed
inventory are preserved. Archive files use content hashes as names; source-plan.json
maps every module to its original name, version, URL, roles and Go h1 checksum.

Verify using Python 3.11+ (stdlib only), supplying the manifest SHA-256 from the
separately delivered receipt:

```sh
python -I verify.py --verify . --sha256 <manifest-sha256-from-receipt>
```

No Git, Docker, Go installation or network is needed for verification. It checks
the exact file list, SHA-256 and sizes, the complete go.sum union, Go h1 file-content
hashes, installed module identities, source VERSION/LICENSE/PATENTS, Caddy main
and gosu observed files. Archives are read without extracting or executing code.
Keep notes/results outside this directory; extra files cause verification failure.

Trust the separately obtained receipt and verifier before running it: a self-hashed
manifest alone is not an independent signature. HTTPS/download hashes and the
recorded builder evidence are not a new signed sumdb or build attestation.

Remaining: toolchain bootstrap/compiler rebuild, full offline/reproducible image
build, native link graph, other attribution/source gaps and release acceptance.
Go .info proxy metadata, bootstrap binaries and a ready-to-use GOPROXY tree are
not included. This supplement is source material, not an offline build installer.
Third-party licenses remain in their upstream files and the existing notice kit.
