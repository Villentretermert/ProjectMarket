# PM-023 · curl/libcurl в локальном прокси

30 октября 2026 · продолжение D47. Полная PM-023 открыта; 19/24, G05 planned.
По явному ответу владельца опубликован ранее подготовленный отчёт a88ef6a.

## Проверенный охват

Два входа CVE-2026-92392 сохранены отдельно: curl и libcurl 8.22.0-r0
из снимка proxy от 27 октября. Статический результат обоих — needs_review:
наличие пакета доказано, прикладной путь эксплуатации не установлен.
[Реестр с evidence, gaps и ranks](assets/PM-023/dependencies-20261030/static-triage.json).
Применимого SECURITY.md для deploy/apps/api resolver не нашёл.

[Upstream advisory](https://curl.se/docs/CVE-2026-92392.html) описывает
use-after-free при HTTP/2 upload и ответе сервера RST_STREAM. У MarkeTOB
Caddy собран с CGO_ENABLED=0; маршрут идёт к фиксированному api:8000,
healthcheck вызывает BusyBox wget. Наличие curl не доказывает, что этот
upload-путь доступен пользователю. Исправление ниже относится к поставленной
версии зависимости, а не к воспроизведённой атаке на приложение.

## Изменения

- `deploy/Dockerfile.proxy`: оба Alpine-пакета закреплены на **8.23.0-r0**.
  Base digest, Caddy 2.11.7, Go 1.26.10, x/net 0.60.0 и brotli не менялись.
- Сравнение полных APK manifests: изменились только curl и libcurl.
  SHA-256 Caddy совпал до/после; UID, capability restrictions, healthcheck,
  маршруты и каталоги данных сохранены.
- CI проверяет точные версии обоих пакетов и реальный HTTP/2 GET новым
  контейнерным curl с доверенным локальным CA. Проверка host curl сохранена.
- По независимому review исправлена потеря exit status curl: результат сначала
  присваивается отдельной переменной под shell `-e`, затем сравнивается версия.
  Старый аналогичный host probe исправлен в той же границе проверки.

## Проверки и результаты

Сборка proxy PASS. Одноразовый контейнер с отдельным loopback-портом,
временными `/data` и `/config`, read-only/cap_drop/no-new-privileges:
readiness с database=ok, Web, health=healthy, UID10001 и metadata Caddy PASS.
Контейнерный curl согласовал HTTP/2 с доверенным CA; без CA вернул exit60.
Контейнер остановлен, рабочие сервисы этой проверкой не заменялись.

Trivy 0.76.1, база **2026-10-30T01:01:11Z**; старый и новый immutable image
проверены одной базой. Обе выбранные записи отсутствуют в кандидате.
Ни ignore, ни фильтры severity не добавлены.

| Proxy image | Всего записей | Critical | High | Medium | Low | Unknown |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Старый d53232e | 56 | 0 | 4 | 5 | 44 | 3 |
| Кандидат pm023-deps30 | 8 | 0 | 2 | 3 | 0 | 3 |

Ушли 48 записей разных severity, включая два выбранных High. Рост старого
образа с 50 записей 27 октября до 56 связан с новой базой сканера.
Оставшиеся восемь относятся к Go-компонентам Caddy: go-jose v3/v4, chi,
x/crypto и x/net. В этой итерации они не исправлены. API/DB/bot/locks
повторно этим запуском не сканировались; актуальный общий счётчик не выводится
путём смешивания двух дат сканирования.

9 focused tests, Ruff check/format и mypy (92 файла) PASS.
Shell substitute подтвердил: старая проверка принимала stdout `2` с exit22;
раздельное присваивание под `-e` сохраняет exit22. Независимый review завершён,
его единственный конкретный дефект исправлен и проверен.

Начальные неуспешные попытки: формат Windows-пути wslpath и разделитель
вывода curl исправлены в временных helper; pytest сначала не смог создать
системный temporary directory, повтор с отдельным workspace basetemp прошёл.
Эти сбои не используются как подтверждение успешных проверок.

[CI40998612689](https://github.com/Villentretermert/ProjectMarket/actions/runs/40998612689)
на **750e506** завершён успешно во всех четырёх jobs: 90 unit + 110 integration
= **200 Python tests**, **54 Chromium scenarios**, Docker startup/recovery,
оба demo-бота, HTTPS/HTTP2 и backup/restore. Два Pydantic warning об alias
`cursor`/`limit` сохранены; ошибок тестов нет. Код API этой итерацией не менялся.
[Точные результаты](assets/PM-023/dependencies-20261030/ci-results.json).

## Локальная установка

**Установлен proxy750e506**, его image ID совпал с проверенным кандидатом.
Перед обновлением запись остановлена; backup восстановлен в отдельном
`marketob-pm023-deps30-restore`/`marketob_pm023_curl_verified`:
**29 таблиц и 10 sequences совпали**, PostgreSQL18.6 →18.6.
Исходная `marketob_pm022` сохранена; её состояние повторно сверено до запуска
писателей. Проверочный restore project остановлен, его volume сохранён.

Только proxy получил новый образ. API/DB/maintenance сохранили контейнеры
и image IDs. Уточнение31октября по timestamped log: Compose повторно запустил
мигратор, результат already current, новых миграций нет. Историческое поле
`migration_executed:false` в JSON не означает отсутствие запуска runner.
Для воспроизводимого Compose новая
конфигурация использует MARKETOB_RELEASE=750e506; неизменённые API/DB/bot
images помечены этим же release tag без пересборки. Caddy CA сохранился.
Backup, предыдущий env и отдельная копия proxy data/config остаются приватными
в `.local/pm023/dependency-delivery-05/`.

После установки HTTPS/Web/регистрация/сессия/Secure cookie/удаление
синтетического аккаунта, реальный HTTP/2 новым curl и UID10001 PASS;
все четыре сервиса healthy. [Проверенный итог](assets/PM-023/dependencies-20261030/local-delivery.json).
При неуспехе helper возвращал бы только прежний proxy, без восстановления
устаревшего backup поверх новых данных. Этот rollback не потребовался.
Первый вызов install helper системным Python завершился на import до изменений;
выполненный запуск использовал проектный `.venv-dev`.

Outcome **fixed** относится к двум выбранным curl/libcurl package/advisory
matches и потере exit status в CI. Отсутствие исходных совпадений установлено
повторным scanner и точной версией пакетов, а совместимость — runtime-проверкой
и полным CI. Воспроизведение исходного UAF/RCE не заявлено.

## Отдельная SSL-копия psycopg

Изолированное чтение существующего API image подтвердило psycopg 3.3.6,
binary implementation, libpq **18.6** и загруженную bundled OpenSSL **3.5.8**.
Python ssl использует системную OpenSSL 3.0.22 с ранее установленным Debian
backport; замена системного пакета не заменяет wheel-библиотеку.

Прослежен основной путь `config.py` → `database.py` → psycopg/libpq.
В [исходнике libpq 18.6](https://github.com/postgres/postgres/blob/REL_18_6/src/interfaces/libpq/fe-secure-openssl.c#L753)
создаётся SSLv23_method context, а [соединение](https://github.com/postgres/postgres/blob/REL_18_6/src/interfaces/libpq/fe-connect.c#L2859)
использует SOCK_STREAM. Это свидетельство TLS/TCP для прямого PostgreSQL-пути;
оно не закрывает другие consumers и остальные advisory OpenSSL.
DTLS-путь CVE-2026-84782 через приложение не установлен.

На дату проверки [стабильный psycopg](https://www.psycopg.org/psycopg3/docs/news.html)
остаётся 3.3.6; 3.3.7 unreleased. Поддерживаемая
[локальная C-сборка](https://www.psycopg.org/psycopg3/docs/basic/install.html#local-installation)
с системным libpq — отдельный вариант поставки, требующий собственных проверок
Linux/Windows и поведения подключения. Драйвер этой итерацией не менялся.

## Доказательства и следующий шаг

[Package/runtime checks](assets/PM-023/dependencies-20261030/proxy-check.json),
[полный сравнительный audit](assets/PM-023/dependencies-20261030/proxy-audit.json.gz),
[SBOM нового proxy](assets/PM-023/dependencies-20261030/proxy.cdx.json.gz),
[psycopg linkage](assets/PM-023/dependencies-20261030/psycopg-linkage.json).
Публичные файлы содержат технические версии/хеши и результаты проверок;
выгрузок аккаунтов, конфигурации с секретами, backup и новых скриншотов нет.

Следующий шаг — разбор оставшихся Go-зависимостей и поставки bundled SSL; notices,
согласованные визуальные доработки и видео сохраняются в плане.
Android, облако и полный L2 остаются отложенными.
