# PM-023 · остаточные зависимости и OpenSSL

27 октября 2026 · продолжение D47. Полная PM-023 открыта;19/24, G05 planned.

## Статический разбор

Разобраны все137 High/Critical записей основных API/proxy/DB образов из снимка
25 октября:24 уникальных CVE. Каждая запись сохранена отдельно в исходном порядке,
включая повторы между бинарными пакетами и образами. Это не137 разных атак.
Отдельный bot image повторяет системные зависимости API и не включён второй раз
в эти137; при обновлении пакетов его итоговый образ также проверяется.

Результат: **0 confirmed,7 not_actionable,130 needs_review**. Последнее означает
не доказанную атаку, а незавершённую проверку условий конкретного вызова.
Применимого SECURITY.md для deploy/apps/api/src resolver не нашёл; использованы
Compose, Dockerfiles, LOCAL_DELIVERY.md, inventory и исходники. Статическая фаза
не запускала приложения, PoC или тесты и не изменяла код.

| Записи | Основание исключения именно указанного компонента |
| --- | --- |
| 2 Critical zlib / CVE-2023-45853 | Debian не собирает contrib/minizip в этом Bookworm zlib. В inventory обоих образов нет minizip/libminizip1. [Debian](https://security-tracker.debian.org/tracker/CVE-2023-45853) |
| 4 High libsystemd0/libudev1 / CVE-2026-16742 | Уязвим systemd-homed; его нет в inventory и среди entrypoints. Присутствие библиотек не означает наличие этого сервиса. [Debian](https://security-tracker.debian.org/tracker/CVE-2026-16742) |
| 1 High libxml2 / CVE-2026-74860 | Claim относится к Python SAX bindings, отсутствующим в PostgreSQL image. C XML interface PostgreSQL — другой путь. [Debian](https://security-tracker.debian.org/tracker/CVE-2026-74860) |

Это статические выводы для конкретных образов, а не исправление их пакетов.
Исходные scanner rows остаются без изменений: ignore/suppression не добавлены.
[Все137 решений, доказательства, gaps, ranks и24 ссылки advisory](assets/PM-023/dependencies-20261027/static-triage.json).

В needs_review сначала ранжированы XML/LDAP/SSL consumers, затем SQLite,
привилегированная инициализация БД и локальные CLI. Severity — не доказательство
достижимости. API принимает проверенный JSON и связывает его как Jsonb через
psycopg; не выполняет XML/XPath или переданный клиентом SQL. API и боты имеют
non-root/cap_drop/no-new-privileges/read-only ограничения. У БД сохраняется
upstream entrypoint с начальной подготовкой прав, поэтому ограничения API нельзя
автоматически переносить на все её пути.

SQLite используется в отдельном журнале бота: SQL фиксирован, значения связаны
параметрами. Это не позволяет закрыть все записи SQLite в иных образах без
проверки транзитивных consumers. RSS использует defusedxml.ElementTree, не
Python libxml2. Backup использует pg_dump/pg_restore с manifest/checksum;
это не универсальный загрузчик чужих tar/LZH/SQLite файлов.

## Доступное обновление

Для CVE-2026-84782 [Debian теперь публикует](https://security-tracker.debian.org/tracker/CVE-2026-84782)
исправленные libssl3/openssl **3.0.22-1~deb12u2**; установленный снимок содержал u1.
Наличие пакетов подтверждено apt metadata в одноразовом контейнере без томов.
[DLA-4859-1](https://security-tracker.debian.org/tracker/DLA-4859-1) содержит также
исправления других OpenSSL advisory. [Upstream описание](https://openssl-library.org/news/secadv/20260929.txt)
требует DTLS retransmission при приостановленной записи. Достижимость через
текущий HTTP/TCP-пилот не доказана; обновление версии проверяется отдельно.

Оба Python Dockerfile теперь наследуют build/final от обновлённого python-base.
PostgreSQL обновляет эти два пакета только в final stage. Используются точные
версии и --only-upgrade, без общего apt upgrade. Сравнение manifests подтвердило:
изменены только libssl3/openssl в каждом из трёх образов. Хеш бинарника PostgreSQL
не изменился. CI проверяет Debian revision: upstream строка OpenSSL3.0.22 сама
по себе не показывает установленный backport.

## Повторный audit и проверки candidate

Trivy0.76.1 с БД2026-10-27T13:12:49Z: old/new сравниваются в одном запуске.
Из каждого API/DB/bot image ушли обе записи CVE-2026-84782; всего12 записей
разных severity на образ. Основные образы720→696 строк; отдельный бот255→243.
Для актуального основного набора остаются5 Critical/130 High. Это сырые счётчики,
семь статических исключений из них не вычтены.

Прокси не менялся: новый scanner DB показывает50 записей вместо прежних2,
включая2 High curl/libcurl CVE-2026-92392 (fix8.23.0-r0). Рост относится к
обновлению сведений сканера, не к замене proxy image. Эти новые записи не включены
задним числом в статический разбор137 входов. Их проверка — следующий шаг.

В API отдельно проверена реально загруженная библиотека wheel psycopg-binary:
**OpenSSL3.5.8**, которую apt не заменяет. Это отдельный пробел системного package
audit; исправление всех копий OpenSSL не заявлено. Текущая стабильная psycopg
[3.3.6](https://www.psycopg.org/psycopg3/docs/news.html),3.3.7 ещё unreleased.
Нужны отдельный разбор libpq/TLS пути и выбор поддерживаемой поставки wheel;
DTLS через текущий HTTP/TCP путь не доказан.

- Сборки API/DB/bot и двух Python build stages PASS; Debian версии u2 проверены.
- 33 targeted tests PASS,4 Docker-only skips; Ruff/format/mypy92files PASS.
- Первое сравнение manifests оказалось некорректным из-за WSL интерпретации
  шаблона dpkg-query. Повтор со стандартным выводом установил точные2 изменения;
  исходный неуспех не используется как доказательство.
- Полный CI и локальная установка ещё ожидаются; рабочий пилот пока dac119f.

[Сравнение и image IDs](assets/PM-023/dependencies-20261027/comparison.json),
[package changes и SSL linkage](assets/PM-023/dependencies-20261027/package-comparison.json),
[полный audit](assets/PM-023/dependencies-20261027/audit.json.gz), SBOM
[API](assets/PM-023/dependencies-20261027/api.cdx.json.gz),
[DB](assets/PM-023/dependencies-20261027/db.cdx.json.gz),
[бот](assets/PM-023/dependencies-20261027/bot.cdx.json.gz),
[proxy](assets/PM-023/dependencies-20261027/proxy.cdx.json.gz).
Команды и границы: [runbook audit](../privacy/DEPENDENCY_AUDIT.md).
Android/облако/полный L2 не возобновлены.
