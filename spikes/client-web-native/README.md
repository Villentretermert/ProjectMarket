# MarkeTOB Web / native feasibility spike

PM-002. Public synthetic data only; no backend, authentication or actual orders. Web has been exercised in the browser. Android build and device tests are deferred by the owner; native source is **unverified**.

From the repository root (Node 24, Python 3.14):

```powershell
npm.cmd --prefix spikes/client-web-native ci
npm.cmd --prefix spikes/client-web-native run build
python -m http.server 8552 --bind 127.0.0.1 --directory spikes/client-web-native/dist
```

Open `http://127.0.0.1:8552`. Select a channel, save it, switch chart/table, reload. After the first successful load, the service worker can serve the public shell when the server is stopped. It never caches API routes. The bundled data is illustrative and is not a private offline cache implementation.

The local demo profile changes a label only. Local accounts and access checks belong to PM-006. “Send request” demonstrates Pending and explicitly does not submit an order.

Android source: `android/`. Native `NewsWidgetPlugin` writes bounded public headlines to app-private preferences; `NewsWidgetProvider` renders RemoteViews and opens an allowlisted `marketob-demo://channel/news` route. There is no Firebase plugin/configuration. No APK/AAB or real widget verification is claimed. Resume according to [Android setup](../../docs/setup/ANDROID_USB.md).

Build dependencies are pinned by `package-lock.json`. Capacitor 8.4.3 was selected after 8.5.3 CLI dependency audit reported a vulnerable transitive uuid dependency. `npm audit` on the selected lock returned zero findings at the time of the check; this is not a complete security assessment.
