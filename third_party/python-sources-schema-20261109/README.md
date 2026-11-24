# Python runtime source supplement

24 November 2026. This supplement covers all 30 distinct third-party PyPI
name/version pairs in the installed Linux/amd64 API and bot images of
schema-20261109 (29 API entries, 6 bot entries, 5 shared).
The [manifest](manifest.json) binds each sdist to the installed inventory and
the exact release commit's `uv.lock`: URL, compressed size, SHA-256 and image IDs.

The local archive is 14,735,360 bytes, SHA-256:

```text
102d3b95e5800c49bae69f3ea9f81411e58948af1cd66d59976a0cbf1ee9cd5f
```

It contains 34 regular outer members: 30 unchanged upstream sdists plus
`manifest.json`, `inventory.json`, `uv.lock`, `verify.py`. Each sdist's root
`PKG-INFO` matches its installed name/version. Package code is never executed.
Upstream symlinks inside sdists remain opaque data and are never followed.

See [collection/recipient instructions](../../docs/licensing/PYTHON_RUNTIME_SOURCES.md)
and [verification receipt](../../docs/task-results/assets/PM-023/python-sources-20261124/receipt.json).

Coverage is **partial**: these are version-matched published source inputs,
not proof of how the shipped binaries were built. The six native-package
sdists overlap the earlier Python/Rust kit; 24 runtime sdists are additional.
CPython, Go/toolchain inputs, the complete transitive build dependency closure,
native feature/link maps, full rebuild and external release acceptance remain
open. Existing source/Docker kits are unchanged; deliver this as a supplement.
