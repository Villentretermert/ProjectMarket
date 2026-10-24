# PM-023 · исправление отзыва при полной очереди

24 октября 2026 · D45. Finding `resource-exhaustion.membership-outbox-fanout`
из исходного scan `358f6f14-3d8a-4ada-8482-046a4f86966f`. Полная задача PM-023
остаётся in_progress, счётчик 19/24. Этот отчёт относится к одному исправлению.

## Изменение и воспроизведение

На исходном коде регрессионный тест с 20 000 pending rows получил HTTP429 на
DELETE grant. Та же транзакция не могла зафиксировать отзыв. Первая попытка самого
тестового примера использовала слишком короткий idempotency key и остановилась
раньше; после исправления данных теста проблема воспроизведена именно на DELETE.

Новый helper `access_changes.py` атомарно двигает delivery watermark/floor вместе
с правами. Изменены callers в auth_routes, teams, bot_routes и channels (общий
publish также покрывает rollback). Убран fanout только из access reconciliation;
обычный notify_status и ingestion сохранены. Retention больше не уменьшает floor.
Новых таблиц, ослабления авторизации или изменения Bot API нет.

[ADR-0016](../adr/0016-permission-invalidation.md) объясняет границу и компромисс
глобального resync. Web использует существующую обработку410; runtime JS не менялся.

## Проверки

- Ruff/format/mypy: PASS, 88 Python source files.
- `pytest tests/test_access_invalidation.py tests/test_updates.py tests/test_privacy.py
  tests/test_teams.py tests/test_identity.py tests/test_bots.py tests/test_channels.py
  tests/test_actions.py tests/test_operations.py`: **76 PASS, 126,08 с**.
- Новые14 проверок:9 маршрутов с полной pending queue; оба capacity caps с очередью
  другого workspace; rollback при сбое marker; поздний commit/retention floor;
  no-op/denied/multichannel operations. Чужие строки и receipts сохраняются.
- Первое ожидание нового теста ошибочно считало ACK состоянием processing. Проверка
  исправлена согласно существующему контракту: ACKed queued остаётся queued при
  одной лишь смене Admin→Editor. Логика заявки приложения не менялась.
- Дополнительные усиленные controls: **3 PASS, 18,08 с**. Обычный ingest отклонён
  при обоих caps; grant восстановлен до освобождения pending queue.
- Реальный Web/API/боты, Edge: **49 PASS**, без page errors; новый сценарий
  использует настоящий `resync_required` после изменения прав и проверяет сохранённый
  My Space layout. [JSON](assets/PM-023/queue-fix/browser-results.json).
- Независимый read-only review: конкретных surviving bypasses/regressions не найдено.
  Это одна проверка текущего diff, не повтор полного security scan.
- CI40076750756: Python Windows/Ubuntu, PostgreSQL API/backend и Docker PASS;
  браузер остановился в старой проверке My Space: assertion читал временно скрытый
  источник до окончания resync. Проверка теперь ждёт возвращения разрешённого
  товара; проверки отозванной новости и отсутствия её названия сохранены.
  Повторный CI 40077334919 на3009316 прошёл все 4 jobs:185 Python tests
  (81unit+104integration),49 Chromium scenarios, backend faults и Docker/HTTPS/restore.
  [Статусы и числа](assets/PM-023/queue-fix/ci-results.json). Outcome: **fixed**.

Фактический экран после resync: title, layout v2 и источник сохранены.

![My Space после пересинхронизации](assets/PM-023/queue-fix/access-resync-space.png)

[Закрытое подтверждение после отзыва](assets/PM-023/queue-fix/privacy-revoked-dialog.png).

Предыдущие assertions на конкретные revoke outbox rows заменены на проверку410,
текущих прав и marker. Legacy hints старой версии всё ещё проходят privacy cleanup;
эту совместимость проверяют явные fixture rows. Триггер admission отключается
только на время заполнения случайных тестовых схем, затем включается до HTTP.
Рабочий пилот и его БД для этих тестов не использовались.

## Ограничения

Полный L2, Android/виджет, Google/Firebase/облако остаются отложенными.
Глобальная пересинхронизация может повысить нагрузку при частых изменениях прав;
полученный результат не доказывает новые SLO. Ответы export/delete P1–P3 приняты как D46 и реализуются отдельно.
На момент отдельной проверки Docker был6b3ffb5; затем [D46](PM-023-account-privacy.md)
установлен как a7deaab после CI/backup/restore. Исходный запечатанный scan сохранён
без переписывания; результат исправления фиксируется отдельно.
