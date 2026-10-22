# Локальная разработка MarkeTOB

PM-005/006 · 22 октября 2026. Работают health и локальная identity; это ещё не весь продукт.
Auth, B2B-профиль и grants описаны в [IDENTITY](../api/IDENTITY.md). Bot API, страницы,
продуктовый клиент и worker — следующие задачи. Для identity нужна PostgreSQL и миграции.

## Чистая копия и Python на Windows

Нужны Git и Python **3.14.7**. Интернет требуется для первой установки зависимостей;
Google/Firebase, бот-токены и облачный сервер не нужны. Из корня `ProjectMarket`:

```powershell
python -m venv .local/uv
.local/uv/Scripts/python.exe -m pip install uv==0.13.5
$env:UV_PROJECT_ENVIRONMENT = '.venv-dev'
.local/uv/Scripts/uv.exe sync --locked
.local/uv/Scripts/uv.exe run --locked marketob-api
```

Переменная `UV_PROJECT_ENVIRONMENT` отделяет backend от старого spike-окружения
`.venv`. Задавайте её в каждом новом терминале. `uv.lock` закрепляет транзитивные
зависимости и хеши; `--locked` запрещает незаметно изменить разрешённый набор.
Не нужен `Activate.ps1` или изменение PowerShell execution policy.

Откройте [проверку API](http://127.0.0.1:8000/health/live):
`{"status":"ok","service":"marketob-api","version":"0.1.0"}`.
Остановка — `Ctrl+C` в терминале сервера. Можно открыть второй терминал:

```powershell
.venv-dev/Scripts/python.exe scripts/smoke_api.py --database not_configured
.venv-dev/Scripts/python.exe bots/examples/check_gateway.py
```

Без PostgreSQL `/health/ready` **намеренно возвращает 503** и `not_configured`.
Это честная диагностика отсутствия хранилища, а не ошибка установки Python.
Подключённая, но недоступная БД даёт `unavailable`; liveness остаётся 200.
Все ответы health имеют `Cache-Control: no-store` и не показывают DSN/пароли.

Необязательная `.env` читается из текущего каталога. Переменные окружения имеют
приоритет. Образец `.env.example` содержит имена, не действующие секреты.
`MARKETOB_HOST` по умолчанию `127.0.0.1`, `MARKETOB_PORT` — 8000.
Для уже установленного PostgreSQL добавьте локальный `MARKETOB_DATABASE_URL`
в `.env`; URL со спецсимволами требует percent-encoding. Неверная конфигурация
останавливает CLI с кодом 2 без печати значений. Обычные тесты игнорируют `.env`.

## Linux / macOS

При установленных Python 3.14.7 и uv 0.13.5:

```sh
uv sync --locked
uv run --locked marketob-api
```

По умолчанию uv использует `.venv`. При необходимости отделить старое окружение:
`export UV_PROJECT_ENVIRONMENT=.venv-dev`. Команды проверки ниже одинаковы
для всех систем, если `uv` доступен в PATH.

## Docker Compose: API и PostgreSQL

На Windows нужен работающий Docker с **Linux containers** и Compose v2.
Docker на компьютере владельца при PM-005 отсутствует; его установка, системная
виртуализация и перезапуск компьютера этой задачей не выполняются.
Контейнерный сценарий проверяется отдельно в Linux CI.

Из корня репозитория, после установки Docker:

```powershell
python scripts/dev_env.py
docker compose config --quiet
docker compose up --build --detach --wait --wait-timeout 120
python scripts/smoke_api.py --database ok
```

Генератор создаёт случайный локальный пароль в игнорируемой `.env`, не печатает
его и не перезаписывает существующий файл. При уже существующей `.env` заполните
`POSTGRES_PASSWORD` локально: рекомендуется URL-safe значение, созданное этим
генератором. Не копируйте пустой пароль из `.env.example`.
Compose без пароля завершается ещё на проверке конфигурации.

API доступен только на `127.0.0.1:8000`; PostgreSQL **не публикует порт хоста**.
API работает непривилегированным пользователем, в read-only файловой системе;
пароль передаётся при старте, не встраивается в образ. `.dockerignore` разрешает
только исходники API, метаданные workspace и lockfile. Не используйте
`docker compose config` без `--quiet` в публичных логах: раскрытая конфигурация
может содержать локальный пароль.

```powershell
docker compose ps
docker compose down
```

`down` сохраняет именованный volume PostgreSQL. Не добавляйте `--volumes`, если
данные нужно сохранить. Не меняйте пароль существующего volume одним изменением
`.env`: PostgreSQL использует его при первоначальной инициализации; действующий
пароль меняется внутри БД. PostgreSQL 18 хранит данные под `/var/lib/postgresql`.

При занятом порте задайте `MARKETOB_PORT=8100` в `.env`, затем для smoke используйте
`--url http://127.0.0.1:8100`. Для прямого Python это меняет порт сервера, для
Compose — порт хоста; внутренний порт контейнера остаётся 8000.

## Проверки разработчика

Windows в этом workspace: вместо `uv` используйте `.local/uv/Scripts/uv.exe`
после установки `UV_PROJECT_ENVIRONMENT` из первого раздела. Для проверки
зависимостей этого отдельного окружения используйте
`uv pip check --python .venv-dev/Scripts/python.exe`; pip-команды uv не используют
`UV_PROJECT_ENVIRONMENT`.

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest -q -m "not integration"
uv run --locked python -m scripts.smoke_local
uv pip check
python scripts/validate_requirements.py
```

`smoke_local` запускает установленный пакет из пустой временной директории на
свободном loopback-порту, проверяет настоящий HTTP и отдельный процесс-пробник,
затем останавливает только свой сервер. Unit-тесты проверяют отказ БД через
контролируемый mock; реальная БД проверяется Docker job через HTTP, остановку и
восстановление PostgreSQL. Не выдавайте mocks за проверку транзакций.
Дополнительный `pytest -m integration` требует явно заданный
`MARKETOB_TEST_DATABASE_URL` для отдельной тестовой БД; без него он пропускается.

CI выполняет lint, format, strict typing, тесты и startup smoke на Windows/Linux,
затем отдельно строит образ и проверяет PostgreSQL, отказ/восстановление и restart
API. PM-006 добавляет отдельный PostgreSQL job для миграций и identity/grants.
Приём сообщений, очередь и нагрузочные свойства проверяются следующими задачами.

## Раскладка кода

| Каталог | Содержание сейчас | Следующий шаг |
|---|---|---|
| `apps/api/src/marketob_api` | Настройки, health, identity/grants, миграции | PM-007: боты/ключи |
| `apps/client` | Граница клиента; ссылка на принятый UX | PM-013–020 |
| `packages/contracts` | Устанавливаемые PM-004 схемы и reference model | Проверки реального API |
| `packages/bot-sdk` | Граница независимого SDK | PM-011 |
| `bots/examples` | Независимый HTTP connectivity probe | PM-011: каталог/новости |
| `deploy`, `compose.yaml` | Dockerfile, API + migration + PostgreSQL | PM-021: эксплуатационная поставка |
| `tests` | Поведение конфигурации и health | Проверки будущих модулей |

`/openapi.json` сервера описывает только реализованные health/identity-маршруты.
Полный проектный контракт находится в `packages/contracts/src/contracts/openapi.json`.
Swagger/Redoc CDN не подключены. Английский UX-прототип продолжает отдельно
запускаться по [инструкции PM-003](../../design/prototype/README.md).

## Миграции и identity · PM-006

Compose сам выполняет `python -m marketob_api.migrate` одноразовым сервисом перед
API. Для прямого Python с заданным `MARKETOB_DATABASE_URL` сначала выполните:

```sh
uv run --locked python -m marketob_api.migrate
uv run --locked marketob-api
```

Применённые миграции неизменяемы; повторный запуск безопасен, checksum выявляет
изменение применённого файла. Для нового порта/UI-origin задайте точный JSON-массив
`MARKETOB_ALLOWED_ORIGINS` в .env. Wildcard, HTTP вне loopback и URL с путём не принимаются.
[API identity и правила локального аккаунта](../api/IDENTITY.md) — обязательный контракт
для будущего клиента; пока нет формы входа в продуктовом Web-интерфейсе.

На одноразовом тестовом экземпляре API можно выполнить
`python scripts/smoke_identity.py`: создаёт случайный smoke-аккаунт, проверяет HTTP
и деактивирует его; оставляет tombstone зарезервированного username. Не печатает
пароль/cookie/CSRF. При необходимости укажите `--url`.

Для integration-тестов с Docker (только тестовая БД, не реальные данные):

```sh
docker compose -f compose.yaml -f deploy/compose.test.yaml up db --detach --wait
uv run --locked python scripts/test_postgres.py
docker compose -f compose.yaml -f deploy/compose.test.yaml down
```

Override явно открывает порт БД **только на loopback:55432**. Обычный compose его
не публикует. Тесты используют случайные схемы, затем удаляют только их; запускать
их надо на отдельной тестовой БД. Скрипт читает локальный пароль из .env без вывода.
Для уже существующей тестовой БД можно задать `MARKETOB_TEST_DATABASE_URL` локально.

При этой задаче Windows-тесты дополнительно выполнены на переносимой PostgreSQL
18.6 из EDB под .local. Она не входит в Git/образ и не заменяет воспроизводимый
Compose: исходник и причины пути описаны в ADR-0005. Локальный test server пока
нужен для следующих PM-007/008; установка системной службы не выполнялась.
