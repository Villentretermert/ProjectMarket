# MarkeTOB interactive design

English UI with synthetic fixtures. No backend, external requests, real accounts, real keys or payments. State lasts for one page session. PM-003 defines UX; product implementation follows in PM-013–020.

From the repository root:

```powershell
.venv/Scripts/python.exe -m http.server 8554 --bind 127.0.0.1 --directory design/prototype
```

Open http://127.0.0.1:8554/. Use Channels, My Space and Studio; open Preview states for errors and the widget mockup. The user badge opens the local sign-in mockup. Share a layout before importing the in-session code MT-DEMO-001.

`prototype.js` holds simulated transitions; `styles.css` defines responsive tokens; `index.html` supplies semantic landmarks and a local-only asset policy. Android build/device validation is deferred.
