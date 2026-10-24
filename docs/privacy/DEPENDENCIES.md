# Инвентаризация зависимостей · PM-023

24 октября 2026. [Машиночитаемый снимок](dependency-inventory.json) получен из
`uv.lock`, `apps/client/package-lock.json` и Docker/Compose declarations без
изменения зависимостей. Он включает SHA-256 исходных manifest/lock файлов
после нормализации CRLF → LF (одинаково для Windows/Linux),
60 Python entries (включая локальные workspace/dev packages), 3 Node entries
и закреплённые container digests. Это не полный SBOM системных пакетов образа.

| Компонент | Закрепление / назначение |
| --- | --- |
| Python / uv | candidate3.14.9 / 0.13.5, `uv sync --locked` |
| API | FastAPI 0.159.1, Uvicorn 0.54.0, pydantic-settings 2.16.1 |
| БД | psycopg 3.3.6, psycopg-pool 3.3.3; candidate Docker PostgreSQL 18.6 с digest |
| Пароли / контракты | argon2-cffi 25.1.0, jsonschema-rs 0.57.1, локальный marketob-contracts |
| Браузерные тесты | Playwright 1.62.1; Node не нужен для работы Web |
| HTTPS | candidate Caddy 2.11.7 с digest |
| Собственные пакеты | marketob-api, marketob-contracts, marketob-bot-sdk, marketob-demo-bots |

Полный список транзитивных версий — в JSON; wheel/sdist hashes и разрешение
версий — в исходном `uv.lock`. Browser lock также фиксирует integrity.
Native PostgreSQL 18.6 совпадает по minor с новым candidate Docker;
приёмка обеих сред указывается отдельно. Frontend входит в Python API как
статические HTML/CSS/JS, внешние CDN в runtime не нужны.

Следующий шаг PM-023 выполнен отдельно: [dependency review и обновление pins](../task-results/PM-023-dependencies.md).
Trivy0.76.1 проверил lock/build pins и фактические images, PyPI — declared license
metadata. Для locks57Python/3Node advisory не найдено; в системных/vendored
компонентах images они есть, включая Critical/High. Глобальный runtime pip удалён.
Доступны SBOM и точное сравнение; это не full security/legal clearance.
[Повторение проверки](DEPENDENCY_AUDIT.md). Установка candidate и CI отмечаются
отдельно в отчёте; базовый inventory не подменяет эти evidence.
