# Инвентаризация зависимостей · PM-023

24 октября 2026. [Машиночитаемый снимок](dependency-inventory.json) получен из
`uv.lock`, `apps/client/package-lock.json` и Docker/Compose declarations без
изменения зависимостей. Он включает SHA-256 исходных manifest/lock файлов,
60 Python entries (включая локальные workspace/dev packages), 3 Node entries
и закреплённые container digests. Это не полный SBOM системных пакетов образа.

| Компонент | Закрепление / назначение |
| --- | --- |
| Python / uv | 3.14.7 / 0.13.5, `uv sync --locked` |
| API | FastAPI 0.159.1, Uvicorn 0.54.0, pydantic-settings 2.16.1 |
| БД | psycopg 3.3.6, psycopg-pool 3.3.3; Docker PostgreSQL 18.4 с digest |
| Пароли / контракты | argon2-cffi 25.1.0, jsonschema-rs 0.57.1, локальный marketob-contracts |
| Браузерные тесты | Playwright 1.62.1; Node не нужен для работы Web |
| HTTPS | Caddy 2.10.2 с digest |
| Собственные пакеты | marketob-api, marketob-contracts, marketob-bot-sdk, marketob-demo-bots |

Полный список транзитивных версий — в JSON; wheel/sdist hashes и разрешение
версий — в исходном `uv.lock`. Browser lock также фиксирует integrity.
Native PostgreSQL 18.6 на машине разработчика отличается от версии Docker;
приёмка обеих сред указывается отдельно. Frontend входит в Python API как
статические HTML/CSS/JS, внешние CDN в runtime не нужны.

Обновление pinned versions, проверка известных CVE и лицензий/транзитивных
системных пакетов здесь **не выполнялись**. Статический scan исходников не
подменяет эти проверки. Перед внешним релизом нужны актуальные advisory/license
проверки именно собранных образов и повтор CI после изменения зависимостей.
