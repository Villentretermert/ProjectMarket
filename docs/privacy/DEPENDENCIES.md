# Инвентаризация зависимостей · PM-023

24 октября 2026. [Машиночитаемый снимок](dependency-inventory.json) получен из
`uv.lock`, `apps/client/package-lock.json` и Docker/Compose declarations без
изменения зависимостей. Он включает SHA-256 исходных manifest/lock файлов
после нормализации CRLF → LF (одинаково для Windows/Linux),
60 Python entries (включая локальные workspace/dev packages), 3 Node entries
и закреплённые container digests. Это не полный SBOM системных пакетов образа.

| Компонент | Закрепление / назначение |
| --- | --- |
| Python / uv | 3.14.9 / 0.13.5, `uv sync --locked` |
| API | FastAPI 0.159.1, Uvicorn 0.54.0, pydantic-settings 2.16.1 |
| БД | psycopg 3.3.6, psycopg-pool 3.3.3; Docker PostgreSQL 18.6 с digest |
| Пароли / контракты | argon2-cffi 25.1.0, jsonschema-rs 0.57.1, локальный marketob-contracts |
| Браузерные тесты | Playwright 1.62.1; Node не нужен для работы Web |
| HTTPS | Caddy 2.11.7 base digest; пересборка Go1.26.10, x/net0.60.0, brotli1.2.1-r0 |
| Startup helper БД | gosu1.19, архив с checksum, пересборка Go1.26.10 |
| Собственные пакеты | marketob-api, marketob-contracts, marketob-bot-sdk, marketob-demo-bots |

Полный список транзитивных версий — в JSON; wheel/sdist hashes и разрешение
версий — в исходном `uv.lock`. Browser lock также фиксирует integrity.
Native PostgreSQL 18.6 совпадает по minor с установленным Docker;
приёмка обеих сред указывается отдельно. Frontend входит в Python API как
статические HTML/CSS/JS, внешние CDN в runtime не нужны.

Следующий шаг PM-023 выполнен отдельно: [dependency review и обновление pins](../task-results/PM-023-dependencies.md).
Trivy0.76.1 проверил lock/build pins и фактические images, PyPI — declared license
metadata. Для locks57Python/3Node advisory не найдено; в системных/vendored
компонентах images они есть, включая Critical/High. Глобальный runtime pip удалён.
Доступны SBOM и точное сравнение; это не full security/legal clearance.
[Продолжение27октября](../task-results/PM-023-dependencies-20261027.md): установлен d53232e,
Debian libssl3/openssl3.0.22-1~deb12u2. Отдельная OpenSSL3.5.8 в wheel psycopg
не заменяется apt; её применимость/поставка остаётся в следующем разборе.

[Повторение проверки](DEPENDENCY_AUDIT.md). [Продолжение25октября](../task-results/PM-023-dependencies-20261025.md):
установлен dac119f, CI PASS;32 выбранные High/Critical записи устранены.
Новый audit включает Dockerfile.db и фактические итоговые образы. Базовый inventory
от24октября сохраняет исторические declarations и не подменяет эти evidence.
