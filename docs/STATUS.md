# Текущее состояние

**Дата:** 22 октября 2026. **Завершено:** 15/24 задач пилота, 0/4 развития.
**G02:** закрыта, все 12 ответов приняты. **После G02:** 4/4, PM-009–012 завершены.
**G03:** закрыта, все 13 ответов сохранены. Разрешён весь блок PM-013–016. После G03: 3/4; PM-013–015 done, PM-016 in_progress. Следующая контрольная точка G04 после PM-016.

- Работают локальные аккаунты, сессии, B2B и права доступа; регистрация ботов и индивидуальные ключи; приём данных и хранение истории/квитанций по 30 дней.
- Готовы версии оформления, публикация и откат, snapshots с проверкой прав и ETag; Request purchase, GET/ACK/result, unknown и сверка результатов.
- Python SDK, независимые каталог/RSS-боты, инструкция запуска и Docker profile проверены.
- [CI PM-012](https://github.com/Villentretermert/ProjectMarket/actions/runs/39835253441): все 4 jobs PASS, 117 тестов, реальные сбои API/БД/worker/ботов и восстановление.
- Локальный baseline: 100 ботов, 10 читающих сессий, 3 000/3 000 сообщений за 180,139 с; p95 приёма 295,02 мс, чтения 253,76 мс. После restart сохранены все 3 000 receipt/outbox. Это API baseline, не полный L2/UI SLO.
- PM-013: рабочий Web /app/, local login, каналы, новости/товары/графики, заявки и восстановление после потери ответа. [CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39846617703) 118 tests + 14 Chromium сценариев PASS, Edge PASS. Далее PM-014 Studio/команды, PM-015 избранное, PM-016 My Space, затем G04.
- PM-014 Studio принята: [CI 39853394634](https://github.com/Villentretermert/ProjectMarket/actions/runs/39853394634), 125 tests и 24 Chromium scenarios PASS; локальный Edge PASS. PM-015 принята: [CI 39854053654](https://github.com/Villentretermert/ProjectMarket/actions/runs/39854053654), 130 tests и 29 Chromium scenarios PASS; Edge PASS. PM-016 My Space начата.
- Android SDK/сборка/USB и Google/Firebase/облако отложены владельцем. Docker локально отсутствует, проверен в Linux CI. Переносимая PostgreSQL работает на loopback:55432.
- Доставка outbox в клиент — PM-018, backup — PM-021, полный L2/burst/monitoring — PM-022, приватность и релизная проверка — PM-023.

[G03](reviews/G03/README.md) · [Отчёт PM-012](task-results/PM-012.md) · [Боты](setup/PILOT_BOTS.md) · [Стенд](setup/BACKEND_LAB.md) · [План](ROADMAP.md).
