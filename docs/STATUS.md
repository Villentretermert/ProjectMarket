# Текущее состояние

**Дата:** 22 октября2026. **Завершено:**12/24 задач пилота,0/4 развития.
**G02:** закрыта, все12 ответов приняты. **После G02:**4/4, PM-009–012 завершены.
**G03:** презентация готовится. PM-013 не начинается до ответов или явного разрешения.

- Работают локальные accounts/sessions/B2B/grants, bots/keys, ingestion,30/30day retention, versions/publish/rollback и snapshots с правами/ETag.
- Request purchase/quantity1, GET/ACK/result, unknown/reconciliation, idempotency и outbox реализованы.
- Python SDK, независимые каталог/RSS боты, private setup, Docker profile проверены.
- PM-012 CI39835253441: все4 jobs PASS,117 tests, реальные process crashes/API/DB/worker restart и Python/Docker bots PASS.
- Локальный baseline:100 bots,10 readers,3000/3000 сообщений за180.139с, p95 ingest295.02мс/read253.76мс. После restart все3000receipt/outbox сохранены. Это API baseline, не полный L2/UI SLO.
- Web PM-003 остаётся demo. Следующий блок PM-013–016: Web, Studio/команды, избранное, My Space. Командные роли обязательны до внешнего пилота.
- Android SDK/build/USB и Google/Firebase/cloud отложены владельцем. Docker локально отсутствует, проверен Linux CI. PostgreSQL переносимая loopback55432.
- Live/outbox delivery PM-018, backup PM-021,30minL2/burst/monitoring PM-022, privacy/release PM-023 ещё не приняты.

[Отчёт PM-012](task-results/PM-012.md) · [Боты](setup/PILOT_BOTS.md) · [Стенд](setup/BACKEND_LAB.md) · [План](ROADMAP.md).
