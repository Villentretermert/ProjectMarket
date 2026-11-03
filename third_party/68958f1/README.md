# Third-party notice snapshot 68958f1

Collected 3 November 2026 from local Linux amd64 Docker images.
This sidecar is a partial notice collection. Complete source materials and
Alpine/bundled-code attribution remain open. See [distribution preparation](../../docs/licensing/DISTRIBUTION.md).

## Reading the texts

Run the integrity check from the repository root. It requires Python only.

```text
python -m scripts.collect_notices --verify --output third_party/68958f1
```

Extract `texts.tar.gz` into a new directory with an archive viewer.
`inventory.json` maps each original source path to `texts/<SHA-256>.txt` in
that directory. No paths from the image are extracted onto the host.
The archive contains only regular text files named by their hashes.
Texts are preserved verbatim, including copyright, NOTICE and patent files.

## Coverage

| Image | Immutable ID | Component occurrences | With notice files |
| --- | --- | --- | --- |
| api | `sha256:7a25ca664062d8f81018757e1cb542653536143971a6f5d73bcca9b10c17728b` | 136 | 136 |
| bot | `sha256:18eaf77c5ce756ee83d6053a943ea1420667a2f8f374051ac7a5366959083e68` | 104 | 104 |
| db | `sha256:07aa878e696f9eca7e46515ba052c6f80f1372d09686cfb7b71ba49054b5a52f` | 151 | 151 |
| proxy | `sha256:031c3f1f15156d1a0054dbe3328220c81ca0090b9dab5384fd0210d88672164b` | 193 | 161 |

584 component occurrences represent 377 unique ecosystem/name/version triples.
259 unique text files are deduplicated by their exact SHA-256.
32 package entries have no notice files in the installed image. Absence here
does not mean that a package has no license. Alpine metadata below records its
declared expression without substituting it for the full text.

## Missing package texts

| Package | Version | Declared license | Source package |
| --- | --- | --- | --- |
| alpine-baselayout | 3.7.2-r0 | GPL-2.0-only | alpine-baselayout |
| alpine-baselayout-data | 3.7.2-r0 | GPL-2.0-only | alpine-baselayout |
| alpine-keys | 2.6-r0 | MIT | alpine-keys |
| alpine-release | 3.23.7-r0 | MIT | alpine-base |
| apk-tools | 3.0.8-r0 | GPL-2.0-only | apk-tools |
| brotli-libs | 1.2.1-r0 | MIT | brotli |
| busybox | 1.37.0-r30 | GPL-2.0-only | busybox |
| busybox-binsh | 1.37.0-r30 | GPL-2.0-only | busybox |
| c-ares | 1.34.9-r0 | MIT | c-ares |
| ca-certificates | 20261020-r0 | MPL-2.0 AND MIT | ca-certificates |
| ca-certificates-bundle | 20261020-r0 | MPL-2.0 AND MIT | ca-certificates |
| curl | 8.23.0-r0 | curl | curl |
| libapk | 3.0.8-r0 | GPL-2.0-only | apk-tools |
| libcap | 2.78-r0 | BSD-3-Clause OR GPL-2.0-only | libcap |
| libcap-getcap | 2.78-r0 | BSD-3-Clause OR GPL-2.0-only | libcap |
| libcap-setcap | 2.78-r0 | BSD-3-Clause OR GPL-2.0-only | libcap |
| libcap-utils | 2.78-r0 | BSD-3-Clause OR GPL-2.0-only | libcap |
| libcap2 | 2.78-r0 | BSD-3-Clause OR GPL-2.0-only | libcap |
| libcrypto3 | 3.5.9-r0 | Apache-2.0 | openssl |
| libcurl | 8.23.0-r0 | curl | curl |
| libidn2 | 2.3.8-r0 | GPL-2.0-or-later OR LGPL-3.0-or-later | libidn2 |
| libpsl | 0.21.5-r3 | MIT | libpsl |
| libssl3 | 3.5.9-r0 | Apache-2.0 | openssl |
| libunistring | 1.4.1-r0 | GPL-2.0-or-later OR LGPL-3.0-or-later | libunistring |
| mailcap | 2.1.54-r0 | Public Domain | mailcap |
| musl | 1.2.5-r24 | MIT | musl |
| musl-utils | 1.2.5-r24 | MIT AND BSD-2-Clause AND GPL-2.0-or-later | musl |
| nghttp2-libs | 1.69.0-r0 | MIT | nghttp2 |
| scanelf | 1.3.8-r2 | GPL-2.0-only | pax-utils |
| ssl_client | 1.37.0-r30 | GPL-2.0-only | busybox |
| zlib | 1.3.2-r1 | Zlib | zlib |
| zstd-libs | 1.5.7-r2 | BSD-3-Clause OR GPL-2.0-or-later | zstd |

## Repeating collection

The original Go builders must be available. The collector refuses a builder
whose binary differs from the runtime image. Network access is disabled in
all inspection containers. No application volumes or user credentials are used.
The optional source directory contains a separately downloaded jsonschema_rs
sdist whose URL and SHA-256 are pinned in `uv.lock`.

```text
python -m scripts.collect_notices --wsl Ubuntu --release 68958f1 --proxy-builder marketob-proxy-builder:deps31-candidate --db-builder marketob-db-builder:notices-68958f1 --python-sdist-dir .local/pm023 --output .local/notices-new
```

Omit `--wsl Ubuntu` with a native Docker CLI. Output must be a new directory
inside the checkout. Without a builder or source archive, missing evidence
remains visible. Exit 0 means collection succeeded, including its stated gaps.
A failed collection leaves `INCOMPLETE.txt` and must not be distributed.
`--verify` validates byte integrity and references only. Neither mode certifies
license compatibility or corresponding-source completeness.

The local source archive can be downloaded from the exact `sdist.url` of
`jsonschema-rs` in `uv.lock`. The collector verifies `sdist.hash` before reading
license files and never executes the archive's code.
