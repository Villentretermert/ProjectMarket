# ADR-0013 · локальные обновления открытого клиента

PM-018, 23 октября 2026. Реализовано; доказательства приёмки в
[отчёте задачи](../task-results/PM-018.md).

## Решение

Foreground polling каждые 2s использует существующие HttpOnly сессии и PostgreSQL.
SSE/WebSocket потребовали бы отдельного управления долгими соединениями; при
локальном пилоте polling проще проверять и переносить в будущий Android runtime.
Уведомления только внутри открытого приложения; ОС/provider/background отложены.

Нельзя использовать исходный identity sequence outbox как порядок доставки.
PostgreSQL выделяет sequence независимо от commit; Read Committed видит только
зафиксированные строки. Следовательно, транзакция с меньшим номером может стать
видимой после большего. Источники: [sequence functions](https://www.postgresql.org/docs/current/functions-sequence.html)
и [transaction isolation](https://www.postgresql.org/docs/current/transaction-iso.html).

Короткая отдельная транзакция сериализует присвоение delivery_sequence только
зафиксированным outbox-строкам. Она освобождает общий lock до проверок каналов.
Поздний commit получает новый номер доставки. Payload содержит только hint;
клиент повторно читает разрешённый snapshot или статус собственной заявки.

Cursor HMAC привязан к сессии и имеет rolling TTL 10 минут. Bootstrap получает
watermark **до** snapshot; после истечения/сбоя snapshot resync обязателен. Клиент
продвигает cursor только после применения результата и дедуплицирует hints в RAM.
Каждый poll проверяет текущие права. Наличие favorite/layout reference/preferences
не выдаёт доступ к данным. Явно видимые источники проверяются и без нового события.

Preferences задают только toast, не отключают обновление данных. По умолчанию
включён request.status только для собственной заявки. News/catalog opt-in.
Тип события без текста/цены/сводки подходит для будущей provider-границы; токен
устройства не является сессией или правом на канал. Android должен повторять те же
bootstrap/resync/authorization/clear-on-logout правила; реальной сборки здесь нет.

## Проверка и границы

Обязательны late commit, replay/expired/foreign cursor, фильтрация по правам и
подпискам, revocation/restoration, потеря сети, preservation editor, отказ OS
permission и замер durable receipt → DOM. L2/burst остаются PM-022; результаты
фактического локального профиля фиксируются отдельно.

Присвоение delivery order выполняется по требованию авторизованного poll, партиями
до1000 строк. GET сканирует50 строк за страницу плюс до50 watch invalidations.
Исходные outbox hints пока сохраняются физически; PM-023 явно включает их cleanup
и cursor floor. Срок10min ограничивает гарантию replay независимо от retention.
Память клиентской дедупликации ограничена1000 IDs и живёт в текущем экране; после
перезагрузки нет обещания ровно одного toast. Актуальные данные восстанавливаются
через snapshot, поэтому отсутствие журнала уведомлений не теряет состояние бота.
