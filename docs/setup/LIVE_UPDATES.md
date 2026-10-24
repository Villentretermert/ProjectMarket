# PM-018 · live updates на локальном компьютере

Для прямого Python остановите старый API и из корня проекта, с настроенной `.env`
для вашей PostgreSQL, примените миграции и запустите API:

```powershell
.venv-dev/Scripts/python.exe -m marketob_api.migrate
.venv-dev/Scripts/python.exe -m marketob_api
```

Сам API автоматически миграции не применяет. Compose выполняет migration service
при запуске обновлённого образа. Отдельный брокер/облако не нужен.
В Channels, открытом канале и My Space индикатор **Live** означает работающий
foreground polling. После сообщения бота источник обновляется без Refresh.

В канале нажмите **Events**. **News updates** и **Catalog changes** включаются
отдельно. **My request status** включён по умолчанию только для собственных заявок.
**Save** сохраняет настройки аккаунта; другая его сессия использует те же правила.
При запрете уведомлений ОС всё работает: приложение показывает собственный toast,
разрешения браузера/ОС не запрашиваются. Закрытое приложение уведомлений не получает.

My Space обновляет данные независимо от заголовка, layout и Undo. При неизвестном
результате autosave остаётся прежний Retry save. После изменения прав PM-023
все открытые потребительские экраны кратко скрывают содержимое и перечитывают
разрешённые источники; недоступные остаются скрытыми. Открытые dialogs закрываются.
При потере связи также скрывается всё содержимое источников.
Личная структура сохраняется, статус меняется на **Reconnecting · Content hidden**.
Восстановление связи запускает bootstrap и проверку доступа. После длительного
простоя вкладка также перечитывает данные. Studio сохраняет ручной Refresh.

## Проверки

```powershell
$env:MARKETOB_BROWSER_CHANNEL='msedge'
.venv-dev/Scripts/python.exe -m scripts.smoke_web --connection-file .local/postgres-dev/connection.json --output .local/live-check
.venv-dev/Scripts/python.exe -m scripts.live_load --connection-file .local/postgres-dev/connection.json --output .local/live-load
```

`live_load` по умолчанию выполняется 900s: десять ботов и десять видимых браузерных
контекстов, 100 msg/min, 80% news/product и20% chart, один из десяти клиентов создаёт
заявку раз в минуту. Источники синтетические. Секреты только в памяти/закрытом
игнорируемом стенде. После проверки удаляется только созданная временная схема.
`--seconds 60` проверяет измерительный стенд и не заменяет полный L1.

Метрика live — durable HTTP receipt → DOM revision после requestAnimationFrame.
Это отрисовка реального приложения в headless browser, не физическое измерение
пикселей монитора. Read/ingest/action HTTP включают локальный transport overhead.
Отчёт сохраняет длительность, версии, счётчики, payload sizes, p95/p99, ошибки и
размер БД. `--bots 100 --seconds 1800 --burst` запускает полный L2/burst PM-022.
Его актуальная методика, ограничения и эксплуатационные команды описаны в
[OPERATIONS.md](OPERATIONS.md).

[Контракт](../api/LIVE_UPDATES.md) · [Результаты](../task-results/PM-018.md).
