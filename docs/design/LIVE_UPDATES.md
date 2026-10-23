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

## Фактический результат

![Events](../task-results/assets/PM-018/live-events.png)

![My Space](../task-results/assets/PM-018/live-space.png)

Синтетические данные реального локального API, Edge1440×1000. Проверена также
ширина360px. По визуальной проверке флажки выровнены с подписями; активное
соединение отмечено зелёным Live. При загрузке Events controls заблокированы,
чтобы ответ сервера не перезаписывал сделанный пользователем выбор.

Отличие от макета: Live находится общей полосой под navigation, Events открывает
modal. Существующая плотность и структура My Space сохранены. Быстрый
revoke/restore/revoke потребовал отдельного повторного скрытия содержимого даже
при одинаковом hint; dedup подавляет только повторные fetch/toast.

```mermaid
flowchart LR
  Bot[Python / external HTTP bot] -->|POST message| PG[(Snapshot + durable outbox)]
  PG --> Delivery[Post-commit delivery order]
  Delivery --> Auth[Session + current source rights]
  Prefs[(Own preferences)] --> Auth
  Auth -->|GET updates / cursor| Web[Web: Channels + My Space]
  Web -->|Authorized snapshot / GET request| PG
  Web --> Toast[Selected in-app event]
  Auth -. later .-> Android[Android foreground]
  Auth -. later .-> Provider[Background push provider]
  classDef later fill:#eee,stroke:#999,stroke-dasharray:5 5
  class Android,Provider later
```

[Замер L1](../task-results/PM-018-LOAD.md), [пояснительная записка](../task-results/PM-018.md).
