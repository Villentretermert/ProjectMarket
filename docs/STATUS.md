# Текущее состояние

**Дата:** 22 октября 2026. **Завершено:** 8/24 задач пилота, 0/4 задач развития.
**G02:** закрыта; 12 ответов сохранены, PM-009–012 разрешены.
**После G02:** 0/4. PM-009 выполняется.

- PM-001–008 завершены. PM-002 принят в Web-объёме после отсрочки Android владельцем.
- G01 закрыта по явному указанию владельца. Плотность UI подтверждена и сохранена.
- Работают локальный FastAPI, миграции, accounts/sessions/B2B/grants, registry/keys,
  draft-create и ingestion text/data/event/delete. PostgreSQL хранит снимки,
  версии, квитанции и outbox. По G02 retention history/receipts меняется на 30/30 дней; проверка в PM-009.
- [Итоговый CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39802915693):
  все 4 jobs PASS, Windows/Linux, Docker, 26 PostgreSQL + 47 unit/contract tests.
  Локально 73 tests PASS и настоящий HTTP API restart/replay/revoke PASS.
- [Короткий замер](task-results/assets/PM-008/ingestion-burst.json): 100 сообщений,
  4 бота/клиента, 29.55 req/s, p95 222.53ms, 0 errors. Длительный SLO не доказан.
- Docker на компьютере владельца отсутствует; контейнеры проверены Linux CI.
  Переносимая PostgreSQL работает локально на loopback:55432 без системной службы.
- Публикация/consumer snapshots, actions/queue, SDK и пилотные боты ещё впереди.
  Web PM-003 остаётся demo, не подключён к backend. APK/виджет не собраны.
- Пилот локальный. Google/Firebase/облако, Android SDK-лицензия/сборка и USB-проверка
  отложены владельцем. Эти вопросы не нужно задавать повторно.
- После G02 следующий блок: PM-009 → PM-010 → PM-011 → PM-012, затем G03.
  Физическое стирание аккаунтов, backup recovery и длительная нагрузка ещё не готовы.

[G02: презентация, код и вопросы](reviews/G02/README.md) · [Ответы](reviews/G02/answers.md)
· [Запуск](setup/LOCAL_DEVELOPMENT.md) · [План](ROADMAP.md) · [Issues](GITHUB_ISSUES.md).

Результаты: [PM-005](task-results/PM-005.md), [PM-006](task-results/PM-006.md),
[PM-007](task-results/PM-007.md), [PM-008](task-results/PM-008.md).
