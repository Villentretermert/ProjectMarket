# Debian source kit for pilot 68958f1

Use this kit when handing over the Debian and PGDG source packages for the API, bot and database images. It covers all 350 installed Debian package occurrences across those images, matched by exact source package and version. The 95 distinct combinations include two revisions of cyrus-sasl2 and the PGDG builds of postgresql-18 and postgresql-common. [Installed inventory](../68958f1-native/inventory.json) · [Source manifest](manifest.json).

From the repository root, with Python 3.14 and gpgv installed (Git for Windows also supplies gpgv), create a new tar file. Allow about 1.1 GB for the cache and output. The program first authenticates four signed APT releases with the public keyrings from the pinned API image. It matches the Sources indexes, verifies SHA-256 for every downloaded file, and compares each descriptor's source name, version and file list. It checks the finished archive before publishing its filename.

```text
python -m scripts.debian_sources --fetch --cache .local/debian-sources --archive .local/debian-source-kit.tar
```

To repeat using a populated cache, omit `--fetch` and choose a new output name. For a smaller check of the signed package indexes alone, run the following command. It downloads the approximately 9.5 MB Bookworm main index on the first run. The three smaller historical indexes are included alongside their signed releases. Repository mirrors, the Debian Snapshot file service and archive URLs are recorded in the manifest. Downloaded contents must match the SHA-256 in the signed index.

```text
python -m scripts.debian_sources --fetch --indexes-only
```

A recipient can verify the complete kit offline using this repository checkout and the tar file. The package materials are stored under their original pool paths. After verification, extract the desired package directory into an empty folder. Run `dpkg-source -x <descriptor.dsc>` there on Debian to reconstruct the source tree with its packaging changes.

```text
python -m scripts.debian_sources --verify-archive .local/debian-source-kit.tar
```

The kit collected on 5 November 2026 contains 304 pool files and 11 files of metadata. It is 549,560,320 bytes, SHA-256 `d3393b02aa53dd684280ef87ea9a91b10da2f991aa4ec75eab1ce4d427f96ae7`. All 95 source trees extracted with dpkg-source and their Debian changelog versions matched the inventory.

Authentication covers the saved repository signatures, exact package revisions and file bytes. The September security index supplies tzdata 2026c-0+deb12u1. Signature verification here establishes historical provenance. The archived indexes are for source retrieval. Building binaries, testing replacement or relinking and selecting a delivery method for recipients are separate release steps. [Engineering report](../../docs/task-results/PM-023-debian-sources-20261105.md).
