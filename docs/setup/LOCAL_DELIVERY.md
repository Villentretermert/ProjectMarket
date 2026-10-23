# Локальная поставка Web / API / worker · PM-021

23 октября 2026. Android, Google/Firebase и облако отложены владельцем.
Поставка предназначена для одного компьютера, доступ только через loopback.
Фактические проверки и незакрытые критерии: [отчёт](../task-results/PM-021.md).

## Уже подготовленный стенд на этом компьютере

Проверенный проект `marketob-pm021` оставлен работающим. Откройте
[MarkeTOB](http://127.0.0.1:19000/app/) и создайте свой аккаунт через Create account.
Приложение использует восстановленную `marketob_pm022`; прежние БД `marketob_recovered` и `marketob` сохранены.
На стенде есть синтетические проверки/demo, это не публичный сервис.
Приватная конфигурация — `.local/pm021/docker.env`, images закреплены тегом6b3ffb5. PM-022 обновлена через отдельный restore;
backup до обновления находится в игнорируемом `.local/pm022/pre-upgrade-backup`,
предыдущая конфигурация — `.local/pm022/docker-before-upgrade.env`.
Семь основных таблиц сверены до/после, migration011 применена; HTTPS и CLI gauges PASS.

Повторный запуск из корня репозитория в PowerShell:

```powershell
wsl -d Ubuntu -- docker compose --project-name marketob-pm021 --env-file .local/pm021/docker.env -f compose.yaml -f deploy/compose.local.yaml up --detach --no-build --wait --wait-timeout 120
```

Для остановки замените `up ...` на `down`, **без `--volumes`**. Другие проекты
Docker не останавливаются. Для новой чистой установки используйте раздел ниже;
не копируйте пароль/архив из проверочного стенда в публичные документы.

## На этом компьютере без Docker

Рабочий native путь остаётся в [LOCAL_DEVELOPMENT](LOCAL_DEVELOPMENT.md).
Есть Python 3.14.7, PostgreSQL 18.6, локальное окружение `.venv-dev`.
Переносимый PostgreSQL запускается на `127.0.0.1:55432`; пароль не нужен в чате.
Для уже подготовленного экземпляра, из корня репозитория:

```powershell
.local/toolchains/postgres/pgsql/bin/pg_ctl.exe -D .local/postgres-dev/data -l .local/postgres-dev/server.log -o "-h 127.0.0.1 -p 55432" start
$connection = Get-Content -LiteralPath .local/postgres-dev/connection.json -Raw | ConvertFrom-Json
$env:MARKETOB_DATABASE_URL = $connection.url
.venv-dev/Scripts/python.exe -m marketob_api.migrate
.venv-dev/Scripts/python.exe -m marketob_api
```

Если PostgreSQL уже работает, второй `start` не нужен. Во втором терминале
повторите только чтение `$connection` и установку `MARKETOB_DATABASE_URL`, затем
запустите `.venv-dev/Scripts/python.exe -m marketob_api.maintenance`.
Откройте [Web](http://127.0.0.1:8000/app/), зарегистрируйте свой локальный аккаунт.
`Ctrl+C` останавливает API/worker; для штатной остановки БД после них:
`pg_ctl.exe -D .local/postgres-dev/data -m fast stop` из того же каталога инструментов.
Не завершайте PostgreSQL через Task Manager и не удаляйте её data-каталог.

## Docker prerequisites

Нужны Docker Desktop с Linux containers и Compose v2, работающий WSL2/backend,
виртуализация в BIOS и свободное место. На Windows сначала проверить
`wsl --version`, `docker version`, `docker compose version`, `docker info`.
На этом компьютере обнаружены **Ubuntu WSL3.0.3, Docker28.1.1 и Compose2.35.1**.
В Windows PATH Docker отсутствует, но внутри Ubuntu daemon работает.
К каждой приведённой ниже `docker …` команде в PowerShell добавляйте
`wsl -d Ubuntu --` (например, `wsl -d Ubuntu -- docker compose version`).
Для Python backup добавьте `--compose --wsl-distribution Ubuntu`.
Новая установка Docker Desktop и принятие его условий здесь не требуются.
Для чистого компьютера без Docker:
Официальная [инструкция Docker для Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
описывает режим установки и системные требования; это отдельный шаг владельца.

Ориентир для пилота: 4 CPU, 6 GiB памяти Docker VM и 20 GiB свободного диска
**плюс** данные/копии/образы. Это начальный резерв, не результат L2-нагрузки.
Контейнеры ограничены: PostgreSQL 2 GiB, API 512 MiB, worker 256 MiB, proxy 128 MiB;
build cache и optional bots требуют дополнительного места/памяти.
Текущий компьютер: i7-11700K, 16 логических CPU, около 64 GiB RAM, SSD 960 GB.
При проверке WSL доступно 231 GiB в virtual filesystem и 101 GiB на C:;
динамический WSL disk также расходует место хоста. Здесь уже работают сторонние
контейнеры; для проверки используется отдельный Compose project, без их остановки.

## Первый запуск Docker

Из корня `ProjectMarket`:

```powershell
python scripts/dev_env.py
docker compose -f compose.yaml -f deploy/compose.local.yaml config --quiet
docker compose -f compose.yaml -f deploy/compose.local.yaml up --build --detach --wait --wait-timeout 180
python scripts/smoke_api.py --database ok
```

Генератор `.env` сохраняет существующий файл. В новом файле пароль случайный
URL-safe; при ручном пароле требуется корректное URL-encoding для DSN.
Не публикуйте вывод `docker compose config` без `--quiet`: в нём раскрываются секреты.
Если `.env` уже задаёт `MARKETOB_ALLOWED_ORIGINS`, для HTTPS добавьте точный
`https://localhost:8443` к JSON-массиву. При нестандартном `MARKETOB_PORT` также
измените точные HTTP origins и URL проверки.

Откройте [HTTP Web](http://127.0.0.1:8000/app/). `migrate` завершается до запуска
API/worker; readiness требует точного набора/checksum миграций этой версии.
Web упакован в Python API, дополнительный Node-сервер в поставке не нужен.
БД не публикует порт на хост. Proxy, API, worker и migrate непривилегированны;
DB использует официальный entrypoint, который переключается на postgres.
Runtime API/worker/proxy read-only; изменяемые данные лежат в volumes/tmpfs.

```powershell
docker compose -f compose.yaml -f deploy/compose.local.yaml ps --all
docker compose -f compose.yaml -f deploy/compose.local.yaml logs --tail 50 api maintenance
docker compose -f compose.yaml -f deploy/compose.local.yaml down
```

Обычный `down` сохраняет volumes. **Не добавляйте `--volumes` для данных пилота.**
`restart: unless-stopped` восстанавливает сервисы при старте Docker; одноразовый
`migrate` не превращается в постоянно перезапускаемый процесс.
Пароль существующей БД не меняется простым редактированием `.env`.

## Локальный HTTPS

Proxy обслуживает [HTTPS Web](https://localhost:8443/app/) с внутренним CA Caddy.
Корневой сертификат и его закрытый ключ сохраняются в `proxy_data`; сертификат
не является публично доверенным. [Caddy local HTTPS](https://caddyserver.com/docs/automatic-https#local-https)
не требует облака/ACME. Установка CA в хранилище доверия Windows не автоматизирована.
Без неё браузер выдаст предупреждение: используйте HTTP loopback для обычной работы
или отдельно осознанно установите **только публичный** `root.crt` этого экземпляра.

Проверка TLS без изменения доверия всей ОС:

```powershell
New-Item -ItemType Directory -Force .local/delivery
docker compose -f compose.yaml -f deploy/compose.local.yaml cp proxy:/data/caddy/pki/authorities/local/root.crt .local/delivery/root.crt
.venv-dev/Scripts/python.exe -m scripts.smoke_delivery --ca .local/delivery/root.crt
```

Проверка создаёт/деактивирует синтетический аккаунт, проверяет доверенную цепочку,
Web, login и Secure cookie. Для обычной диагностики используйте health без записи.
Не копируйте закрытый ключ CA в Git. При потере volume меняется CA.

## Резервная копия и восстановление

[Подробный runbook](BACKUP_RESTORE.md) содержит команды для native/Compose,
границы копии, проверку checksum, независимую БД и порядок переключения.
Архив не заменяет отдельную копию bot state/env, конфигурации и CA.

## Обновление и откат

1. Запишите Git commit и текущий `MARKETOB_RELEASE`; перед обновлением задавайте
   уникальный tag (например, hash commit), сохраняйте старые API/proxy образы.
   Не используйте пересобранный `local` как единственное средство отката.
2. Соберите candidate images до окна остановки. Остановите внешних/пилотных ботов,
   proxy, API и maintenance. Дождитесь завершения запросов; не допускайте записи
   до завершения проверки candidate. DB оставьте работающей.
3. Создайте и **проверьте восстановлением** backup. Отдельно сохраните остановленное
   состояние ботов. Запишите момент остановки, старый commit/tag и конфигурацию
   локально; эти файлы могут содержать секреты.
4. Выберите новый `MARKETOB_RELEASE`, выполните
   `docker compose -f compose.yaml -f deploy/compose.local.yaml run --rm migrate`.
   При ошибке не запускайте API/worker. Миграции выполняются одной транзакцией.
5. Поднимите candidate через `up --detach --no-build --wait --wait-timeout 180`.
   Проверьте readiness, Web, свой аккаунт и контрольные данные. Только после этого
   разрешайте запись и запускайте ботов.
6. При сбое **до возобновления записи** остановите candidate, восстановите backup
   в новую БД, выберите её через `MARKETOB_DB_NAME`, верните старый tag/checkout и
   `up --detach --no-build --wait`. Исходную БД не удаляйте. Архив проверяется
   инструментом из соответствующего старого checkout, не нового candidate.

Старый код отказывается мигрировать более новую схему. После возобновления записи
возврат к старому backup потеряет новые подтверждённые данные: такой rollback
запрещён этим runbook. Нужны forward fix или проверенный совместимый binary rollback;
down-migrations и PITR этой поставкой не реализованы.

## Боты, Android и перенос

[PILOT_BOTS](PILOT_BOTS.md) описывает отдельные Python-процессы и optional
`compose.bots.yaml --profile demo-bots`; ключи получают через Studio/регистрацию,
env и SQLite-state лежат вне образа/Git. HTTP внутри compose network допускается
только явной конфигурацией пилотных ботов. Не открывайте сеть/порты автоматически.

Android/USB сборка не выполнялась. Будущий debug USB reverse использует loopback;
для LAN нужны доверенный HTTPS, точный origin/адрес, firewall и отдельная проверка.
Текущий `localhost`-сертификат не подходит для LAN IP телефона. Не менять bind на
`0.0.0.0` для обхода настройки. OAuth redirects и HTTPS App Links сейчас не
зарегистрированы: Google/provider и публичный домен отложены, инструкция
[GOOGLE_FIREBASE](GOOGLE_FIREBASE.md) относится к будущему этапу.
На Linux используется тот же Compose; публичный домен/сертификат/ingress
настраиваются отдельным этапом. Облачное хранилище само по себе Docker не запускает.
