# Текущее состояние

**Дата:** 22 октября 2026. **Завершено:** 11/24 задач пилота, 0/4 задач развития.
**G02:** закрыта, все 12 ответов приняты; разрешены PM-009–012.
**После G02:** 3/4; PM-009–011 завершены, PM-012 следующая. После PM-012 обязательна G03.

- Работают FastAPI/PostgreSQL, локальные accounts/sessions/B2B/grants, боты/ключи,
  ingestion, retention history/receipts 30/30 дней, версии/публикация/откат каналов,
  owner inventories и consumer snapshots с проверкой доступа и ETag; durable
  requests/GET/ACK/result, timeout/retention и отзыв pending/ACKed.
- [PM-009 CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39825150008):
  все 4 jobs PASS. Локально **81 тест PASS** (34 PostgreSQL + 47 unit/contract),
  отдельный процесс HTTP API: publish/private/rollback/delete PASS.
- [PM-010 CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39828592091):
  все 4 jobs PASS, 95 tests (48 integration + 47 unit/contract); Docker API/DB
  restart сохраняет unACKed/ACKed заявки и результаты. Локально 94 полный +
  32 итоговый связанный набор PASS.
- PM-011 SDK и каталог/RSS-боты приняты: 117 тестов, Python/Docker smoke PASS.
- Следующая PM-012 полный backend-цикл/сбои/замер 1000 сообщений в минуту.
- G02: Selected users по умолчанию, только Request purchase/quantity=1, без корзины
  и оплаты; живые данные независимо от публикации оформления. Командные роли
  обязательны в PM-014, проверка PM-023 до внешнего пилота. Сейчас workspace owner-only.
- Web PM-003 остаётся demo, не подключён к backend. APK/виджет не собраны.
  Google/Firebase/облако, Android SDK-лицензия/сборка и USB отложены владельцем.
- Docker локально не установлен, проверен в Linux CI. PostgreSQL переносимая,
  loopback:55432. Физическое стирание, backup recovery и длительный SLO ещё впереди.

[G02](reviews/G02/README.md) · [Ответы](reviews/G02/answers.md) ·
[Запуск](setup/LOCAL_DEVELOPMENT.md) · [План](ROADMAP.md) · [Issues](GITHUB_ISSUES.md).

[PM-009](task-results/PM-009.md) · [PM-010](task-results/PM-010.md) ·
[API каналов](api/CHANNELS.md) · [API заявок](api/ACTIONS.md).
