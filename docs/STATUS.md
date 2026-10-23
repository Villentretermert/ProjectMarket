# Текущее состояние

**Дата:** 23 октября 2026. **Завершено:** 19/24 задач пилота, 0/4 развития.
**G02:** закрыта, все 12 ответов приняты. **После G02:** 4/4, PM-009–012 завершены.
**G03:** закрыта, все 13 ответов сохранены. Разрешён весь блок PM-013–016. После G03: 4/4; PM-013–016 done. G04 закрыта по указанию «Продолжай» 23 октября; допущения записаны отдельно. PM-017 done ([CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39924166312)), PM-018 done ([CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39929710247)). После G04: 3/4. Текущий результат:153 tests / 47 browser scenarios PASS; L1 1500/1500 rendered, p95 2.467s/p99 2.625s. PM-019/020 остаются отложены владельцем; G05 ещё не требуется.

- Работают локальные аккаунты, сессии, B2B и права доступа; регистрация ботов и индивидуальные ключи; приём данных и хранение истории/квитанций по 30 дней.
- Готовы версии оформления, публикация и откат, snapshots с проверкой прав и ETag; Request purchase, GET/ACK/result, unknown и сверка результатов.
- Python SDK, независимые каталог/RSS-боты, инструкция запуска и Docker profile проверены.
- [CI PM-012](https://github.com/Villentretermert/ProjectMarket/actions/runs/39835253441): все 4 jobs PASS, 117 тестов, реальные сбои API/БД/worker/ботов и восстановление.
- Локальный baseline: 100 ботов, 10 читающих сессий, 3 000/3 000 сообщений за 180,139 с; p95 приёма 295,02 мс, чтения 253,76 мс. После restart сохранены все 3 000 receipt/outbox. Это API baseline, не полный L2/UI SLO.
- PM-013: рабочий Web /app/, local login, каналы, новости/товары/графики, заявки и восстановление после потери ответа. [CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39846617703) 118 tests + 14 Chromium сценариев PASS, Edge PASS. Studio, избранное и My Space также завершены; материалы G04 ниже.
- PM-014 Studio принята: [CI 39853394634](https://github.com/Villentretermert/ProjectMarket/actions/runs/39853394634), 125 tests и 24 Chromium scenarios PASS; локальный Edge PASS. PM-015 принята: [CI 39854053654](https://github.com/Villentretermert/ProjectMarket/actions/runs/39854053654), 130 tests и 29 Chromium scenarios PASS; Edge PASS. PM-016 принята: [CI 39858054474](https://github.com/Villentretermert/ProjectMarket/actions/runs/39858054474), 137 tests и 36 Chromium scenarios PASS; Edge PASS. My Space сохраняет layout отдельно от данных источников.
- Android SDK/сборка/USB и Google/Firebase/облако отложены владельцем. Docker28.1.1/Compose2.35.1 обнаружены в Ubuntu WSL; локальная поставка PM-021 проверена. Переносимая PostgreSQL работает на loopback:55432.
- Доставка outbox в открытый Web, Events/preferences и resync готовы. [Отчёт PM-018](task-results/PM-018.md). Backup/restore PM-021 проверены; полный L2/burst/monitoring — PM-022, приватность/cleanup и релизная проверка — PM-023.

[G04](reviews/G04/README.md) · [G03](reviews/G03/README.md) · [Отчёт PM-012](task-results/PM-012.md) · [Боты](setup/PILOT_BOTS.md) · [Стенд](setup/BACKEND_LAB.md) · [План](ROADMAP.md).

PM-021 done: локальная Docker-поставка в Ubuntu WSL, HTTPS, backup/restore и restart проверены. [CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39948316689): все4 jobs PASS. [Стенд](http://127.0.0.1:19000/app/) оставлен работающим. Следующая локальная задача PM-022, затем обязательная G05 после20 завершений. Android отложен.

PM-022 in_progress: отдельный локальный стенд, L2/burst и эксплуатационные ограничения; счётчик остаётся19/24 до приёмки.

24 октября: короткий Docker-прогон runtime2008583 с2 API-процессами прошёл все SLO,
2 000/2 000 rendered,live p95=2.084с;burst3 000/3 000,5 100 точных ID после restart.
CI40034156701:162 Python-теста/47 browser scenarios,все4jobs PASS. Выполняется
полный1800с+burst. Предыдущие неудачные повторы сохранены в отчёте PM-022;
задача и G05 не приняты, рабочий пилот пока на6b3ffb5.
