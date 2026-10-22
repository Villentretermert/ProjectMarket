# Система после PM-016

Зелёный — реализовано и проверено. Синий — часть работает, остаётся указанная задача.
Серый — не реализовано либо отложено владельцем. Схема описывает локальный пилот.

```mermaid
flowchart LR
  Web[Web: Channels, Studio, My Space] -->|Сессия / CSRF| API[Python FastAPI]
  Identity[Локальная identity / Owner Admin Editor] --> API
  Bots[Python SDK / каталог / RSS] -->|POST message / GET event / ACK result| API
  API --> DB[(PostgreSQL: сущности и транзакции)]
  Maintenance[Maintenance: retention / timeout] --> DB
  DB --> Outbox[Outbox хранится; доставка PM-018]
  Outbox -.-> Web
  Shared[Обмен шаблонами PM-017] -.-> API
  Android[Android / news widget: отложены] -.-> API
  Cloud[Google / Firebase / облако: отложены] -.-> API
  Ops[Docker CI готов; backup и release PM-021–024] -.-> DB
  classDef done fill:#dff1e8,stroke:#1e7659,color:#213247
  classDef partial fill:#eaf2fd,stroke:#2468bc,color:#213247
  classDef todo fill:#e5eaf0,stroke:#53677f,color:#213247
  class Web,Identity,Bots,API,Maintenance done
  class DB,Outbox,Ops partial
  class Shared,Android,Cloud todo
```

PostgreSQL работает как источник истины; синий цвет обозначает отсутствие завершённой
проверки backup/restore, а не отсутствие базы. FastAPI и Web уже реализуют права,
публикацию, заявки, избранное и личные страницы. Обмен и доставка обновлений —
следующие модули, не новые обязательные микросервисы.

Bot → API → SourceRecord/receipt/outbox — одна транзакция. Браузер получает текущий
разрешённый snapshot. PersonalPage хранит layout с BlockReference; доступ к каждому
источнику проверяется при разрешении snapshot. Request purchase идёт через исходный
канал и независимо перепроверяет права, товар и revision. Боты не имеют доступа к БД.

Web не хранит приватные данные источников на диске. На Refresh, возврате во вкладку
и навигации данные проверяются заново; автоматическое обновление без действий
пользователя пока относится к PM-018. Это существенная граница готовности.
