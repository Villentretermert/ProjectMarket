# G03 · готовность системы

```mermaid
flowchart LR
  Catalog["Каталог Python: готов"] -->|HTTP, индивидуальный ключ| API["FastAPI: готов"]
  RSS["RSS Python: готов"] -->|HTTP, индивидуальный ключ| API
  API --> DB[("PostgreSQL: готова")]
  Worker["Maintenance: готов"] --> DB
  API -. "подключение PM-013" .-> Web["Web: макет, частично"]
  DB -. "доставка PM-018" .-> Live["Foreground updates: не сделано"]
  Web -. "PM-019/020" .-> Android["Android / widget: отложены"]
  Studio["Studio / команды: PM-014"] -.-> API
  Personal["Избранное / My Space: PM-015/016"] -.-> API
  classDef done fill:#dff1e8,stroke:#1e7659,color:#213247
  classDef partial fill:#eaf2fd,stroke:#2468bc,color:#213247
  classDef planned fill:#e5eaf0,stroke:#53677f,color:#213247
  class Catalog,RSS,API,DB,Worker done
  class Web partial
  class Live,Android,Studio,Personal planned
```

API уже хранит версии оформления, данные, квитанции, заявки и outbox.
Maintenance отвечает за retention и таймауты. Он ещё не доставляет outbox в UI.
Боты сохраняют собственный журнал отдельно от PostgreSQL и общаются только через API.
