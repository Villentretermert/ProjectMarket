# CPython source supplement for schema-20261109

This kit contains the official CPython 3.14.9 XZ source archive and observations
from the installed Linux/amd64 API and bot images. Both images record the same
PYTHON_SHA256, matching the SHA-256 published on the Python release page:

```text
e02d9ac21cebda6e46435369744a92c65cc7cd8669697694122cf97ffacd1e53
```

The source LICENSE and Include/patchlevel.h match the installed files exactly.
The installed pyconfig.h, Makefile, compiler/configure flags, interpreter and
shared-library hashes are retained as build observations. No source scripts
are executed. Archive links are never followed or extracted by the verifier.

For verification use Python 3.11+ and obtain the independent manifest SHA-256
from the published receipt linked in the report below. With the reviewed
verifier, run from this directory:

```text
python -I verify.py --verify . --sha256 SHA256_FROM_PUBLISHED_RECEIPT
```

The verifier checks every kit file, both image identities, the source hash,
all archive paths and the two source/runtime byte matches. It needs no Git,
Docker, network or third-party Python packages. Keep the directory unchanged;
put your own notes or results outside it. Upstream source code is provided
under the terms included in the source archive and installed LICENSE.txt.

These observations are not a cryptographic build attestation or a successful
reproducible build. Sigstore signatures have not been verified by this tool.
Full compiler/build inputs, Go inputs, native linking/rebuild and release
acceptance remain open. Existing source and Docker kits are unchanged.

[Official release](https://www.python.org/downloads/release/python-3149/) ·
[Verification report and receipt](https://github.com/Villentretermert/ProjectMarket/blob/main/docs/task-results/PM-023-cpython-20261124.md).
