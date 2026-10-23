# PM-018 · предварительный макет

23 октября 2026, рабочий дизайн перед реализацией. Текущая плотность сохраняется.

```text
My Space                       Live
[Share] [Undo] [Preview] [Refresh]
Space title: My daily space
[News article — updates automatically]
[Product list — current availability]

Channel                        [Events]
  [ ] News updates
  [ ] Catalog changes
  [x] My request status
                         [Save]
```

Polling каждые 2 секунды в открытом клиенте. Данные обновляются отдельно от
редактируемого оформления и заголовка. Собственные статусы заявок выбраны по
умолчанию; остальные события включаются для канала. Toast содержит только общий
тип события. Browser Notification permission не запрашивается.

При сбое: Reconnecting · Content hidden. Затем bootstrap cursor, актуальный snapshot
и продолжение. Недоступные источники остаются placeholders. Logout/скрытие вкладки
останавливают доставку. Background push и Android сейчас не заявляются.

Фактические экраны, метрики и отличия будут добавлены после проверки.
