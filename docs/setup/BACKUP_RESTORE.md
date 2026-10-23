# Backup / restore · PostgreSQL 18

Команды выполняются из корня `ProjectMarket` установленным Python-окружением.
Backend и инструменты PostgreSQL должны соответствовать архиву: в пилоте
восстановление допускается только на том же PostgreSQL major и с точным набором
миграций/checksum этого checkout. Архив другого релиза восстанавливается его
инструментом, затем обновляется обычными миграциями.

## Что сохраняется

`scripts/backup.py` запускает [pg_dump custom format](https://www.postgresql.org/docs/current/app-pgdump.html)
для выбранной схемы приложения, default `public`. Это согласованный snapshot
транзакционных таблиц во время работы БД; остановка нужна для согласованного
обновления приложения/ботов. Миграции во время backup запрещены; инструмент
сверяет историю до/после. Последующие записи в архив не попадают.

Сохраняются аккаунты/password hashes, сессии, grants/команда, bots/credential hashes,
каналы/версии/данные, квитанции/history, заявки/ACK/result, избранное, My Space,
share-коды, preferences, server cursor keys и delivery watermark/sequence.
Файлы: `database.dump` + `manifest.json` (format, время, размер, SHA-256, schema,
PostgreSQL major, миграции). URL/пароль подключения не входят в manifest/argv/вывод.

Это **не зашифрованный** архив. Он содержит приватные данные и серверные секреты;
храните его в `.local/backups` или `backups` (Git ignore) и на защищённом отдельном
носителе с доступом владельца. POSIX mode ограничивается; на Windows наследуются
NTFS ACL каталога — `chmod` не заменяет их проверку. Не прикладывайте архив к issue.
SHA-256 выявляет повреждение, не доказывает происхождение. Восстанавливайте только
свои доверенные копии: PostgreSQL dump содержит исполняемые SQL-определения.

Не входят: PostgreSQL роли/глобальные настройки, другие схемы, внешние blobs,
Docker volumes сторонних ботов, их SQLite/env/API keys, `.env`, release images,
CA proxy. В текущем приложении внешние blobs/расширения БД не используются.
БД должна быть выделена MarkeTOB. Копия схемы не является копией всего компьютера.

## Native на подготовленном компьютере

```powershell
.venv-dev/Scripts/python.exe -m scripts.backup --connection-file .local/postgres-dev/connection.json --pg-bin .local/toolchains/postgres/pgsql/bin create .local/backups/before-update-001
.venv-dev/Scripts/python.exe -m scripts.backup verify .local/backups/before-update-001
.venv-dev/Scripts/python.exe -m scripts.backup --connection-file .local/postgres-dev/connection.json --pg-bin .local/toolchains/postgres/pgsql/bin restore .local/backups/before-update-001 --new-database marketob_recovered_001
```

Либо настройте приватный `MARKETOB_DATABASE_URL` в env/`.env` и опустите
`--connection-file`; URL не передавайте аргументом командной строки. PostgreSQL
client tools можно держать в PATH вместо `--pg-bin`. Нужны права читать всю схему
и `CREATE DATABASE` для restore. Инструмент не создаёт роли и не меняет пароли.

## Compose, без установки pg_dump на Windows

```powershell
.venv-dev/Scripts/python.exe -m scripts.backup --compose create .local/backups/before-update-001
.venv-dev/Scripts/python.exe -m scripts.backup verify .local/backups/before-update-001
.venv-dev/Scripts/python.exe -m scripts.backup --compose restore .local/backups/before-update-001 --new-database marketob_recovered_001
```

`--compose` использует PostgreSQL tools внутри `db`, binary-потоки идут через Python,
не через текстовый PowerShell pipeline. Default source DB — `marketob`. При другом
имени обязательно задайте `--database NAME` (включая уже переключённую recovered DB).
Для другого Compose проекта сохраните его `COMPOSE_PROJECT_NAME`; для custom файлов
повторите `--compose-file FILE` в исходном порядке. Все общие options идут **до**
`create`/`restore`/`verify`. Архив сохраняется на хост, вне database volume.

На текущем ПК Docker находится внутри Ubuntu WSL: добавьте
`--wsl-distribution Ubuntu`. Для отдельного проекта предусмотрены
`--project-name marketob-pm021` и `--env-file .local/pm021/docker.env`;
имя проекта и приватный env-файл должны совпадать с запуском. WSL-команды
выполняются из текущего корня репозитория; Windows-Python не печатает пароль.

Создание отказывает, если каталог уже существует. Незавершённый каталог без
manifest не считается backup. `verify` проверяет файлы/совместимость, но только
**настоящее восстановление** доказывает пригодность архива.

## Восстановление и проверка

Restore создаёт **новую** базу через `CREATE DATABASE … TEMPLATE template0`.
Существующее имя, имя source/system DB, повреждённый archive/manifest и несовместимая
версия отклоняются. [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html)
работает с `--single-transaction --exit-on-error --no-owner --no-privileges`;
объекты принадлежат выполняющей роли. После него проверяются миграции и watermark.
При сбое новая пустая/непринятая БД может остаться для диагностики; исходная не
меняется. Инструмент ничего не переключает и не удаляет автоматически.

1. Запустите отдельный API на loopback с URL новой БД и правильными origins.
   Сначала readiness, затем вход, канал, Request purchase status, My Space,
   share preview и live updates. Не включайте production-ботов в проверочный клон.
2. Для planned upgrade проверьте копию **до** возобновления записи; исходная и
   восстановленная БД никогда не обслуживаются одновременно как активные.
3. Для disaster recovery зафиксируйте RPO: потерян интервал после snapshot.
   Копия возвращает также прежнее состояние grants, credentials и сессий. До
   открытия доступа сверяйте последующие отзывы/изменения, завершайте старые
   сессии, заменяйте ключи ботов и отзывайте share-ссылки при необходимости.
   Уже выполненные внешние действия сверяйте у ботов по request/event ID; не
   запускайте их повторно вслепую. Exactly-once внешней покупки backup не даёт.
4. Для Compose остановите API/worker/proxy и ботов, задайте
   `MARKETOB_DB_NAME=marketob_recovered_001` в приватной `.env`, затем выполните
   `up --detach --wait` по [LOCAL_DELIVERY](LOCAL_DELIVERY.md). Старую БД сохраните
   до подтверждённой приёмки. Для native замените только имя БД в приватном URL.

## Состояние пилотных ботов

Боты являются независимыми сервисами. Перед offline-копией остановите оба процесса
или `catalog-bot`/`news-bot` контейнеры; скопируйте **весь** state-каталог, включая
SQLite WAL/SHM, и отдельные приватные env. Для контейнера можно использовать
`docker compose -f compose.yaml -f compose.bots.yaml --profile demo-bots cp catalog-bot:/data .local/backups/bots-001/catalog`
и аналогично news-bot. Родительские каталоги создайте заранее. Не копируйте только
один `.sqlite3` у работающего процесса. Внешние боты обслуживают собственные backup
по своим регламентам. Автоматический restore сторонних bot state в PM-021 не входит.

## Регулярность и границы

Рабочая рекомендация пилота: отдельная копия перед обновлением, ежедневная копия
при использовании, проверка восстановления после изменения схемы и периодически.
Это **не установленное расписание**. Носитель в том же компьютере не защищает
от его потери. PITR/WAL archive, шифрование архивов и автоматическая ротация здесь
не реализованы; выберите их перед внешней эксплуатацией с требуемым RPO/RTO.
