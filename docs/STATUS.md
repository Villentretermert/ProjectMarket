# Текущее состояние

**Дата:** 22 октября 2026. **Завершено:** 9/24 задач пилота, 0/4 задач развития.
**G02:** закрыта, все 12 ответов приняты; разрешены PM-009–012.
**После G02:** 1/4; PM-009 завершена, PM-010 выполняется. После PM-012 обязательна G03.

- Работают FastAPI/PostgreSQL, локальные accounts/sessions/B2B/grants, боты/ключи,
  ingestion, retention history/receipts 30/30 дней, версии/публикация/откат каналов,
  owner inventories и consumer snapshots с проверкой доступа и ETag.
- [PM-009 CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39825150008):
  все 4 jobs PASS. Локально **81 тест PASS** (34 PostgreSQL + 47 unit/contract),
  отдельный процесс HTTP API: publish/private/rollback/delete PASS.
- Следующие PM-010 заявки/статусы, PM-011 Python SDK и каталог/RSS-боты,
  PM-012 полный backend-цикл/сбои/замер 1000 сообщений в минуту.
- G02: Selected users по умолчанию, только Request purchase/quantity=1, без корзины
  и оплаты; живые данные независимо от публикации оформления. Командные роли
  обязательны в PM-014, проверка PM-023 до внешнего пилота. Сейчас workspace owner-only.
- Web PM-003 остаётся demo, не подключён к backend. APK/виджет не собраны.
  Google/Firebase/облако, Android SDK-лицензия/сборка и USB отложены владельцем.
- Docker локально не установлен, проверен в Linux CI. PostgreSQL переносимая,
  loopback:55432. Физическое стирание, backup recovery и длительный SLO ещё впереди.

[G02](reviews/G02/README.md) · [Ответы](reviews/G02/answers.md) ·
[Запуск](setup/LOCAL_DEVELOPMENT.md) · [План](ROADMAP.md) · [Issues](GITHUB_ISSUES.md).

[Результат PM-009](task-results/PM-009.md) · [API каналов](api/CHANNELS.md).
