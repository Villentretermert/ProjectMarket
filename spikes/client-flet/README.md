# Python / Flet feasibility spike

PM-002 comparison candidate, public demo fixtures only. Dynamic preview works; static offline delivery has unresolved toolchain/runtime failures in the tested environment. This candidate is not selected for the Web pilot; see [ADR-0001](../../docs/adr/0001-client-stack.md).

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r spikes/client-flet/requirements-preview.txt
$env:MARKETOB_PREVIEW_WEB='1'
.\.venv\Scripts\python.exe spikes/client-flet/src/main.py
```

Open `http://127.0.0.1:8551`. This runs Python on the local server; it is not an offline browser runtime.

Tests: `.\.venv\Scripts\python.exe -m pytest spikes/client-flet/tests -q`.

The packaged client specifies `flet==1.0.4` in `pyproject.toml`; CLI requires Flutter 3.44.8. `flet build web --no-cdn` failed on Windows Dart native hooks, even after moving the SDK to a path without spaces. `flet publish` produced a 76 MB static distribution, then failed during browser startup resolving `pyodide/pyodide.mjs`. Additionally, the generated worker uses micropip to install `flet` requirements at startup; `--no-cdn` alone does not establish a fully self-contained dependency bundle. These failures are recorded, not hidden by patching vendored tools.

For a repeatable `flet publish` experiment use an **absolute** `--distpath`: the CLI resolves relative paths from the Python script directory. Keep generated distributions out of `src/`. Android compilation was explicitly deferred by the owner.
