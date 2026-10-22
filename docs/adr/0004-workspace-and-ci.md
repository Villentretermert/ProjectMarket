# ADR-0004 — Воспроизводимый каркас и проверки

22 октября 2026 · PM-005. Решение развивает ADR-0002 без изменения Bot API.

Python 3.14.7, uv 0.13.5 и workspace из двух пакетов: `marketob-api` и
`marketob-contracts`. Корневой virtual project содержит dev-зависимости. Lockfile
закрепляет весь граф, production sync устанавливает только API. Существующий
Flet spike остаётся отдельно и не влияет на backend-зависимости. Контракт PM-004
перенесён в `packages/contracts/src/contracts`; Python namespace `contracts`
сохранён. Генерируемые JSON не меняются.

FastAPI 0.159.1, Uvicorn 0.54.0, psycopg[binary] 3.3.6,
pydantic-settings 2.16.1. Версии проверены по первичным метаданным PyPI; весь
граф и хеши — в `uv.lock`. Starlette 1.9.0 рекомендует httpx2 для TestClient:
выбран httpx2 2.16.0, чтобы не полагаться на deprecated fallback.
Docker base Python 3.14.7 / PostgreSQL 18.4 закреплены также manifest digest,
проверенными через официальный Docker registry. Обновления — отдельный проверяемый
diff, не плавающий latest.

Health разделён на liveness (без внешней зависимости) и readiness (`SELECT 1`).
Для smoke чистой копии PostgreSQL необязателен, отсутствие настройки даёт 503.
Это не разрешение будущим бизнес-модулям обходить обязательное хранилище.
Worker не запускается пустым циклом: он появится вместе с настоящей очередью.
Самопроверка runtime OpenAPI не объявляет будущие v1-маршруты работающими.

CI: Windows/Linux lint/format/strict typing/unit/contract/startup smoke;
отдельно реальный Compose на Linux с отказом/восстановлением БД и рестартом API.
Docker отсутствует на компьютере владельца, поэтому локальный Python и Linux
Compose имеют отдельные доказательства. Контейнерный тест не заменяет локальную
установку Docker или проверку APK. Production hardening остаётся PM-021.

Альтернативы: один общий venv конфликтует со spike; ручной requirements.txt без
полного графа хуже воспроизводится; отдельный брокер и пустой worker не дают
пользы на этом шаге. Продуктовый frontend пока не копирует демонстрационные данные.

Основания: [uv locking](https://docs.astral.sh/uv/concepts/projects/sync/),
[FastAPI Docker](https://fastapi.tiangolo.com/deployment/docker/),
[Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/),
[PostgreSQL official image](https://hub.docker.com/_/postgres).
