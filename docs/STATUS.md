# Текущее состояние

9 ноября: **все три подзадачи поставки выполнены**. R1 — текущий inventory/binding;
R2 — исправленный source archive 1a3dd882… с Windows/Linux offline verification;
R3 — [чистый Docker/Web запуск](task-results/PM-024-clean-delivery-20261109.md):
5 browser checks, 0 JS errors, ровно 1 confirmed-заявка от Docker Python-бота.
34 focused tests и все четыре задания итогового CI 42663866512 на ca772a3 PASS;
smoke_release отдельно проверен на текущих образах. [Инструкция получателю](setup/CURRENT_DELIVERY.md).
Рабочий пилот не менялся. PM-023/024 открыты, 19/24; отсрочки сохраняются.

Уточнение R2: текущий архив — 1a3dd882… в handover-schema-20261109-02,
после исправления найденного CI различия CRLF/LF в хеше исторического recipe.
34 focused tests и повторная Windows/Linux offline-проверка PASS; текущая
квитанция обновлена, первый tar оставлен для диагностики. Чистый запуск в работе.

9 ноября, PM-023-R2: [исходный комплект schema-20261109](task-results/PM-023-source-kit-20261109.md)
собран и автономно проверен на Windows/Linux. 32 focused tests PASS,
исторический комплект 68958f1 сохранён. Два из трёх пунктов поставки выполнены;
далее PM-024-R1 — чистый запуск. Полный счётчик 19/24 и отсрочки сохраняются.

9 ноября, PM-023-R1: [привязка материалов](task-results/PM-023-release-binding-20261109.md)
к schema-20261109 выполнена. 584 записи/259 texts совпали с исходным реестром;
собственные исходники и native bytes проверены. 25 focused tests PASS.
Следующие подзадачи: новый исходный комплект и чистый запуск для получателя.
Счётчик 19/24, PM-023/024 открыты; прежние отсрочки сохраняются.

9 ноября, PM-023: исправление конкурентного построения схем API **установлено
в schema-20261109**. Регрессионный тест воспроизвёл гонку warning-фильтров;
startup сериализован, HTTP остаётся параллельным. Все четыре задания
[CI 42639942759](https://github.com/Villentretermert/ProjectMarket/actions/runs/42639942759)
PASS: 355 различных Python-тестов и 69 Chromium-сценариев. OpenAPI/31 версия
пакетов сохранены. Backup/restore совпал по 29 таблицам/10 sequences;
DB/proxy/CA сохранены, четыре сервиса healthy. My Space/фото/Meduza/Live/logout,
HTTPS/HTTP2 проверены, news-бот перезапущен и работает.
[Отчёт](task-results/PM-023-schemas-20261109.md). Следующий независимый пункт —
привязка исходного комплекта к новым образам. PM-023 открыта, 19/24; личная
приёмка и отсрочки Android/облака/L2 сохраняются.

9 ноября, **S06 выполнена**. Meduza RU подключена к прежнему новостному каналу и
My Space; английская редакция выбирается конфигурацией. Сохранены layouts, IDs,
ключ и журнал; replay не создаёт ревизий, закрытый доступ проверен. Все четыре
задания [CI 42551266615](https://github.com/Villentretermert/ProjectMarket/actions/runs/42551266615)
PASS: 353 различных Python-теста и 69 Chromium-сценариев. Docker-образ бота
собран и читает RSS; локально работает фоновый Python-бот с периодом 300 секунд.
API/worker photos-20261108 и DB/proxy/CA сохранены, четыре сервиса healthy.
[Дизайн](design/MEDUZA_RSS.md), [отчёт и иллюстрация](task-results/SR-meduza-20261109.md).
Следующий шаг передачи — личная проверка My Space владельцем и замечания к Studio;
помощник подключения пока не согласован. 19/24, Android/облако/L2 отложены.

8 ноября, S05. [Фотографии товаров](task-results/SR-product-photos-20261108.md)
реализованы и **установлены в photos-20261108**. Все четыре задания
[CI 42529571116](https://github.com/Villentretermert/ProjectMarket/actions/runs/42529571116)
прошли: 348 различных Python-тестов и 69 Chromium-сценариев. Backup/restore
совпал по 29 таблицам/10 sequences, DB/proxy/CA и сохранённые My Space layouts
сохранены. Четыре сервиса healthy; установленные фото, Live/logout и HTTPS/HTTP2
проверены. Первый формат PNG ≤96 KiB/512 px; миграций и новых зависимостей нет.
S05 завершена; следующий пункт — Meduza RSS. 19/24, Android/облако/L2 отложены.

8 ноября, S03/S04. Реализован [визуальный каталог блоков My Space](task-results/SR-block-catalog-20261108.md)
с поиском, фильтром типов, превью и Check again для недоступного источника.
63 браузерных сценария, 15 foundation-тестов и Ruff/format/mypy112 прошли.
Docker-кандидат собран, 31 версия зависимостей сохранена. На fe66d3d прошли все
четыре задания [CI 42499457148](https://github.com/Villentretermert/ProjectMarket/actions/runs/42499457148):
310 различных Python-тестов и 63 Chromium-сценария, Docker/HTTPS/HTTP2/restore.
Уточнённый тест позднего ответа и `--catalog-only` повторно дали 9 PASS локально.
После команды продолжить (D50) **установлен API/worker catalog-20261108**.
Backup/restore совпал по 29 таблицам и 10 sequences. DB/proxy/CA сохранены;
четыре сервиса healthy, HTTPS/HTTP2 и прежний demo-аккаунт/My Space проверены.
Первая попытка автоматически откатилась из-за раннего health-check proxy;
повторная с ограниченным ожиданием прошла. Все четыре задания
[CI 42500168800](https://github.com/Villentretermert/ProjectMarket/actions/runs/42500168800)
на 9e2f464 также прошли. S03/S04 завершены; далее фотографии товаров.
Счётчик 19/24, прежние отсрочки сохраняются.

CI предыдущего коммита 2402cf9 с видеодемонстрацией завершён: все четыре задания
[42429842053](https://github.com/Villentretermert/ProjectMarket/actions/runs/42429842053) прошли.

8 ноября, демонстрация PM-024. Записан [ролик My Space на 76 секунд](demos/my-space-20261108/README.md):
товар и новость от разных Python-ботов, избранное, Card/автосохранение/Undo,
заявка и Confirmed. На отдельной Docker-копии 68958f1 прошли пять проверок сценария;
в БД ровно одна заявка, page errors — 0. Тестовые Docker-ресурсы удалены.
Добавлены инструкция личного повторения и сценарий повторной записи.
S09 и выбор лицензии отмечены в SR-2026-10-25; личная приёмка пока не выполнена.
Следующая продуктовая доработка — дизайн визуального каталога блоков S03/S04.
PM-023/024 открыты; **19/24**, отсрочки Android/облака/L2 сохраняются.

8 ноября. Собран комплект исходных материалов 750 786 560 байт с автономной
проверкой SHA-256. Git-снимки содержат точные 593/681 файла; внутри объединены
исходники Debian/Alpine/Python/Rust, уведомления и инструкция замены драйвера.
Реальный tar проверен на Windows и в Linux без сети, включая подписи и все
95 версий исходников Debian. 15 тестов и статический контроль прошли.
На b8e5242 прошли все четыре задания [CI 42425558592](https://github.com/Villentretermert/ProjectMarket/actions/runs/42425558592): 310 различных Python-тестов,
54 сценария Chromium, Docker/HTTPS/HTTP2 и восстановление БД.
[Квитанция и результат](task-results/PM-023-handover-20261108.md). Охват partial, PM-023 открыта, готово 19/24.

7 ноября. Проверена пересборка и замена psycopg-c получателем. Обе C-библиотеки
загрузили новую метку, остальные файлы Python-пакетов и реестр системных пакетов
совпали с baseline. Прошли 13 групп TLS/DB/pool-проверок и 11 тестов рецепта,
Ruff/format/mypy по 109 файлам. Добавлены инструкция и повторение в CI.
На коммите b347869 прошли все четыре задания [CI 42397251222](https://github.com/Villentretermert/ProjectMarket/actions/runs/42397251222), 295 различных Python-тестов,
54 сценария Chromium, повторная сборка изменённого драйвера и Docker/HTTPS/HTTP2/restore.
[Отчёт](task-results/PM-023-replacement-20261107.md). PM-023 открыта, готово 19/24 задач.

5 ноября. Собраны исходные пакеты Debian для всех 95 сочетаний имени и версии
в образах API, бота и БД. Подписи четырёх индексов и байты 304 файлов пакетов
прошли проверку. Все 95 пакетов распакованы, версии changelog совпали.
На коммите b810c17 прошли 4 задания CI, 284 различных Python-теста, 54 сценария Chromium и проверка Docker с HTTPS/HTTP2 и восстановлением БД. [CI 41933635979](https://github.com/Villentretermert/ProjectMarket/actions/runs/41933635979).
[Отчёт и инструкция](task-results/PM-023-debian-sources-20261105.md). PM-023 открыта, готово 19/24 задач.

4 ноября. Для всех 10 пропущенных записей Cargo собраны тексты из архивов
пакетов и сопоставленных коммитов. Два набора вместе содержат 546 различных
текстов. Локально подготовлены и проверены 482 файла исходников и материалов.
70 тестов сборщиков прошли.
Для fdebed8 прошли все четыре задания CI, 277 различных Python-тестов и 54 сценария Chromium. [Проверка в GitHub](https://github.com/Villentretermert/ProjectMarket/actions/runs/41749693035).
 PM-023 открыта, готово 19/24 задач. [Отчёт](task-results/PM-023-crate-gaps-20261104.md).

4 ноября, SBOM и native notices. [Проверены три встроенных SBOM](task-results/PM-023-native-provenance-20261104.md)
и 315 registry occurrences; записаны ELF-версии Rust и подтверждение рецепта
libffi 3.4.6. Новый набор содержит 539 уникальных текстов, все прежние gaps сохранены.
Добавлена offline CI-проверка и повторный сбор с проверкой wheel/архивов.
65 targeted tests, Ruff/format/mypy по 103 файлам и проверка хешей прошли.
[CI 41737007937](https://github.com/Villentretermert/ProjectMarket/actions/runs/41737007937) на 60d440d: все 4 задания PASS, 272 различных Python-теста
и 54 Chromium-сценария; Docker/HTTPS/HTTP2/backup/restore прошли.
Точный Linux link map и воспроизводимость сборок не заявлены. Поставка 68958f1,
19/24 и отсрочки сохранены; полная PM-023 открыта.

3 ноября, Rust/C source notices. [Проверены исходники шести Python-пакетов](task-results/PM-023-embedded-licenses-20261103.md)
и 450 уникальных Rust registry inputs. Пять wheel совпали с native hashes API.
В наборе 522 уникальных текста; 10 source notice gaps и 5 отсутствующих workspace
manifests отмечены отдельно от runtime inventory. 35 targeted tests, Ruff/mypy
по 101 файлу прошли. [CI 41690800155](https://github.com/Villentretermert/ProjectMarket/actions/runs/41690800155)
на b8a3203: все 4 задания PASS, 242 различных Python-теста и 54 Chromium-сценария;
Docker/HTTPS/backup/restore и новая проверка notices на обеих ОС прошли.
Точный Rust build graph/toolchain и libffi provenance — следующий подэтап. Поставка 68958f1, 19/24 и отсрочки сохранены.

3 ноября, продолжение. [Alpine source notices](task-results/PM-023-alpine-licenses-20261103.md)
добавлены для 28 из 32 пакетов. Проверены 20 origins, 167 Git blobs и все 152
checksum inputs. В наборе 298 уникальных текстов. Локальный архив исходников
содержит 187 проверенных файлов. Четыре пробела атрибуции остаются открытыми.
20 targeted tests и Ruff/mypy по 99 файлам прошли. [CI 41687143893](https://github.com/Villentretermert/ProjectMarket/actions/runs/41687143893)
на bf767d1 прошёл все 4 задания: 227 различных Python-тестов и 54 Chromium-сценария,
Docker/HTTPS/backup/restore. Привязка уведомлений проверена на Windows и Ubuntu.
Следующая независимая работа — встроенные Rust/C-компоненты Python-библиотек.
Рабочая поставка 68958f1 и счётчик 19/24 сохранены. Полная PM-023 открыта.

**Предыдущий результат — первый сбор уведомлений**

**Дата 3 ноября 2026. Завершено 19/24 задач пилота, после G04 3/4.**
Выбрана Apache-2.0. Четыре Python wheel содержат LICENSE/NOTICE и SPDX metadata.
Собран [реестр лицензий](task-results/PM-023-licenses-20261103.md) поставки 68958f1,
377 уникальных компонентов и 259 текстов. 32 Alpine notices и материалы исходников
ещё открыты. 11 focused tests, Ruff/mypy97files, offline wheel/lock и hashes PASS.
[CI41680762892](https://github.com/Villentretermert/ProjectMarket/actions/runs/41680762892) на e813e77 прошёл все4jobs,
218 Python/54 Chromium, Docker/HTTPS/backup/restore и wheel notices на двух ОС.
Следующий шаг PM-023 — Alpine notices, встроенные зависимости и соответствующие
исходники. Рабочая поставка не обновлялась. Полная PM-023 и G05 остаются открытыми.

**Предыдущий результат 2 ноября**

**Дата:** 2 ноября 2026. **Завершено:** 19/24 задач пилота, 0/4 развития.
Проверены обе открытые записи OpenLDAP. Все 22 сценария в одноразовом API-образе
прошли. В прямом профиле пилота наблюдалось только подключение к PostgreSQL.
В дополнительном профиле воспроизведены авария при принудительном отказе
памяти и принятие чужого SAN при совпадающем CN через LDAPv3 referral.
Строгий режим SAN отверг подмену и принял правильный сертификат. Применимость
к внешней установке зависит от её настроек и возможности вызвать отказ памяти.
Четыре сервиса healthy, HTTPS readiness 200. Следующий пункт PM-023 —
лицензионные уведомления. [Проверка двух случаев](task-results/PM-023-ldap-20261102.md).

**Предыдущий результат:** [Kerberos/OpenLDAP triage](task-results/PM-023-native-triage-20261101.md).
30 новых package/advisory записей (12 CVE):28 not_actionable в закреплённом
Linux API image,2 needs_review,0 confirmed. Статическая оценка; scanner276
не подавлен, runtime не менялся. Открыты LDAP allocation-failure и TLS identity
proof gaps; затем остальные base findings и notices. PM-023 остаётся открытой.

**Последняя поставка:** [Linux psycopg C](task-results/PM-023-psycopg-c-20261101.md).
Docker API использует system libpq18.6/OpenSSL3.0.22 с Debian security revision;
native Windows остаётся binary. Inventory и изолированные TLS/pools/cancel PASS.
Локально95 unit PASS/2 Linux-only skips, Ruff/mypy95files PASS.
CI41309440467 на68958f1: все4jobs PASS,207 Python/54 Chromium.
**Установлен API/maintenance68958f1**: restore29таблиц/10sequences совпал;
исходная БД, DB/proxy image/container IDs и CA сохранены. HTTPS/HTTP2 PASS,
4services healthy; мигратор не запускался, новых миграций нет.
API scanner246→276:30 дополнительных Kerberos/LDAP matches, без подавлений;
удаление SSL bundle доказано inventory, а не счётчиком CVE. PM-023 открыта.

**Предыдущая работа:**
**Предыдущая проверка:** [native SSL psycopg](task-results/PM-023-psycopg-20261031.md).
Добавлен повторяемый Python inventory и проверки CI. Локальные Windows/Linux
проверки complete;14 tests/Ruff/mypy94files PASS. CI41239002094 на665a00e —
все4jobs PASS,205 Python/54 Chromium; новый inventory PASS во всех3средах CI.
Linux wheel использует libpq18.6/SSL3.5.8, Windows wheel18.4/SSL3.6.4.
Драйвер не обновлялся:3.3.7 ещё unreleased. Следующий подэтап — отдельный
Linux-кандидат psycopg[c] с контролем libpq/SSL и совместимости; CVE не закрыта.

**Предыдущая поставка:** [Go-зависимости proxy](task-results/PM-023-dependencies-20261031.md).
**Установлен proxy b202024**: chi5.4.0/go-jose/v4 4.1.7/x/net0.62.0.
CI41215407434 все4jobs PASS,200 Python/54 Chromium;9 focused tests/Ruff/mypy PASS.
Restore29таблиц/10sequences совпал; исходная БД, API/DB/maintenance и CA сохранены.
HTTPS/Web/Secure session/HTTP2 PASS,4services healthy. Мигратор повторно запущен
Compose, already current; новых миграций нет, schema_migrations совпал.
Trivy proxy8→4: три go-jose/v3 остаются, OpenPGP отсутствует в import graph.
Bundled SSL psycopg/base findings, notices и визуальные доработки остаются в плане.
Ниже — историческая поставка30октября.

**Предыдущая работа:** [curl/libcurl proxy](task-results/PM-023-dependencies-20261030.md).
**Установлен proxy750e506**, curl/libcurl8.23.0-r0. CI40998612689 все4jobs PASS:
200 Python/54 Chromium. Restore29таблиц/10sequences совпал; API/DB/maintenance
сохранили контейнеры и image IDs, исходная БД/CA сохранены;4services healthy.
HTTPS/Web/Secure session/HTTP2 проверены; новые миграции не применялись.
Одной базой Trivy proxy 56→8 записей, выбранные два High отсутствуют;
остаются 2 High/3 Medium/3 Unknown в Go-компонентах. Это счётчик только proxy,
API/DB/bot/locks новым запуском не пересканировались.
Поставка psycopg с отдельной OpenSSL3.5.8 остаётся предметом следующего разбора.
Предыдущий отчёт a88ef6a опубликован по явному согласию владельца.

Ниже — подтверждённая поставка и снимок аудита 27 октября.
**Продолжение:** [остаточные зависимости/OpenSSL](task-results/PM-023-dependencies-20261027.md).
137 статических решений:7 not_actionable,130 needs_review; raw scanner сохранён.
**Установлен d53232e**, Debian OpenSSL3.0.22-1~deb12u2. CI40532313119 все4jobs PASS,
200 Python/54 Chromium. Backup/restore29таблиц/10sequences совпали, исходная БД
сохранена; HTTPS/HTTP2 и existing My Space/Live/privacy/export PASS,4services healthy.
Новая база scanner показывает5 Critical/130 High в основных образах;
proxy curl/libcurl и bundled SSL psycopg требуют следующего разбора.
Ниже — ранее установленный результат25октября, не новая проверка27октября.
По запросу владельца подготовлен [обзор статуса](reviews/STATUS-2026-10-25/README.md)
в PPTX/PDF с пояснениями и 12 отдельными вопросами. G05 остаётся planned,
после G04 3/4. Все [ответы S01–S12](reviews/STATUS-2026-10-25/answers.md) получены:
разрешено продолжение зависимостей PM-023, [доработки](follow-ups/STATUS-2026-10-25.md)
запланированы отдельно. Локальная поставка обновлена и проверена 25 октября.
**Предыдущая поставка25октября:** [PM-023 Go dependencies](task-results/PM-023-dependencies-20261025.md).
Кандидаты proxy/gosu собраны Go1.26.10; x/net0.60.0 и brotli1.2.1.
Повторный audit: все32 выбранные High/Critical отсутствуют; основные образы
169→137 High/Critical (5 Critical/132 High).
**Ранее установлен dac119f:** CI40187348787 все4jobs PASS,200 Python/54 Chromium.
Backup/restore18.6:29таблиц/10sequences совпали; оригинальная БД сохранена.
HTTPS/HTTP2, existing demo login/My Space/Live/privacy/export PASS;4services healthy.
В locks57Python/3Node advisory не найдено; в images остаются Critical/High,
полная PM-023 не принята. Следующий P0: применимость оставшихся base findings,
затем notices и согласованные доработки/видео. Android/облако/L2 не возобновлены.

**Текущий gate:** полный L2 PM-022 отложен владельцем до свободного компьютера
(D43). Нагрузочный стенд остановлен. Не запускать новый L2 без продолжения владельца.
**G02:** закрыта, все 12 ответов приняты. **После G02:** 4/4, PM-009–012 завершены.
**G03:** закрыта, все 13 ответов сохранены. Разрешён весь блок PM-013–016. После G03: 4/4; PM-013–016 done. G04 закрыта по указанию «Продолжай» 23 октября; допущения записаны отдельно. PM-017 done ([CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39924166312)), PM-018 done ([CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39929710247)). После G04: 3/4. Текущий результат:153 tests / 47 browser scenarios PASS; L1 1500/1500 rendered, p95 2.467s/p99 2.625s. PM-019/020 остаются отложены владельцем; G05 ещё не требуется.

**Последний результат D46:** реализованы личный JSON export, передача workspace
Owner → Admin и удаление с паролем + DELETE. [Отчёт](task-results/PM-023-account-privacy.md).
187 локальных tests PASS +4 Docker-only skips; contract25 и targeted7 PASS,
54 Edge-сценария PASS. [CI 40078644698](https://github.com/Villentretermert/ProjectMarket/actions/runs/40078644698):
191 tests/54 Chromium, все 4 jobs PASS. P1–P3 отвечены.
**Прежняя поставка D46 — a7deaab**, была установлена после backup/restore:29 таблиц / 10 sequences
совпали; HTTPS и существующий demo My Space/Live/privacy/export проверены.
Все 4 services healthy; прежняя БД marketob_pm022 сохранена.
Исправление очереди отдельно принято по [CI 40077334919](https://github.com/Villentretermert/ProjectMarket/actions/runs/40077334919):185 tests/49 Chromium, все 4 jobs PASS.
Ниже сохраняется хронология предыдущих этапов; её ожидания superseded D45/D46.

- Работают локальные аккаунты, сессии, B2B и права доступа; регистрация ботов и индивидуальные ключи; приём данных и хранение истории/квитанций по 30 дней.
- Готовы версии оформления, публикация и откат, snapshots с проверкой прав и ETag; Request purchase, GET/ACK/result, unknown и сверка результатов.
- Python SDK, независимые каталог/RSS-боты, инструкция запуска и Docker profile проверены.
- [CI PM-012](https://github.com/Villentretermert/ProjectMarket/actions/runs/39835253441): все 4 jobs PASS, 117 тестов, реальные сбои API/БД/worker/ботов и восстановление.
- Локальный baseline: 100 ботов, 10 читающих сессий, 3 000/3 000 сообщений за 180,139 с; p95 приёма 295,02 мс, чтения 253,76 мс. После restart сохранены все 3 000 receipt/outbox. Это API baseline, не полный L2/UI SLO.
- PM-013: рабочий Web /app/, local login, каналы, новости/товары/графики, заявки и восстановление после потери ответа. [CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39846617703) 118 tests + 14 Chromium сценариев PASS, Edge PASS. Studio, избранное и My Space также завершены; материалы G04 ниже.
- PM-014 Studio принята: [CI 39853394634](https://github.com/Villentretermert/ProjectMarket/actions/runs/39853394634), 125 tests и 24 Chromium scenarios PASS; локальный Edge PASS. PM-015 принята: [CI 39854053654](https://github.com/Villentretermert/ProjectMarket/actions/runs/39854053654), 130 tests и 29 Chromium scenarios PASS; Edge PASS. PM-016 принята: [CI 39858054474](https://github.com/Villentretermert/ProjectMarket/actions/runs/39858054474), 137 tests и 36 Chromium scenarios PASS; Edge PASS. My Space сохраняет layout отдельно от данных источников.
- Android SDK/сборка/USB и Google/Firebase/облако отложены владельцем. Docker28.1.1/Compose2.35.1 обнаружены в Ubuntu WSL; локальная поставка PM-021 проверена. Переносимая PostgreSQL работает на loopback:55432.
- Доставка outbox в открытый Web, Events/preferences и resync готовы. [Отчёт PM-018](task-results/PM-018.md). Backup/restore PM-021 проверены; полный L2/burst/monitoring — PM-022, приватность/cleanup и релизная проверка — PM-023.

[G04](reviews/G04/README.md) · [G03](reviews/G03/README.md) · [Отчёт PM-012](task-results/PM-012.md) · [Боты](setup/PILOT_BOTS.md) · [Стенд](setup/BACKEND_LAB.md) · [План](ROADMAP.md).

PM-021 done: локальная Docker-поставка в Ubuntu WSL, HTTPS, backup/restore и restart проверены. [CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39948316689): все4 jobs PASS. [Стенд](http://127.0.0.1:19000/app/) оставлен работающим. Следующая локальная задача PM-022, затем обязательная G05 после20 завершений. Android отложен.

PM-022 in_progress: отдельный локальный стенд, L2/burst и эксплуатационные ограничения; счётчик остаётся19/24 до приёмки.

24 октября: короткий Docker-прогон runtime2008583 с2 API-процессами прошёл все SLO,
2 000/2 000 rendered,live p95=2.084с;burst3 000/3 000,5 100 точных ID после restart.
CI40034156701:162 Python-теста/47 browser scenarios,все 4 jobs PASS. Полный1800с+burst
прерван после13мин по отсрочке владельца. Диагностика и предыдущие неудачные
повторы сохранены в [отчёте PM-022](task-results/PM-022.md). Облегчённый health probe
worker проверен отдельно; [CI d4bd845](https://github.com/Villentretermert/ProjectMarket/actions/runs/40037429124)
успешен во всех4jobs:81unit+86integration=167 Python-тестов и47 browser scenarios.
Новые образы d4bd845 подготовлены. Задача и G05 не приняты, рабочий
пилот пока на6b3ffb5.

24 октября, D44: по команде «Делай следующие задачи» начата независимая
Web/API-часть PM-023: доступ, экспорт и очистка данных. Полная приёмка остаётся
открытой; Android, облако и полный L2 отложены. Счётчик 19/24, G05 ещё не требуется.

PM-023: [частичный результат](task-results/PM-023.md), 29 targeted tests и
48 Edge browser scenarios PASS. Исправлены no-op role notifications, очистка
metadata удалённых сущностей и открытый purchase dialog при отзыве. Статический
scan: один Low finding переполнения общей очереди; общий revoke-path ещё требует
исправления. Два широких патча отклонены автоматической проверкой, не применены;
[предложение](proposals/PM-023-queue-safety.md) ожидает явного разрешения.
Три решения об export/delete ожидают ответов. Рабочий Docker всё ещё на6b3ffb5.
PM-024: [инструкция передачи](setup/PILOT_HANDOFF.md) подготовлена независимо,
полный RC и приёмка владельцем не выполнены. Счётчик остаётся19/24.

[CI 3d82143](https://github.com/Villentretermert/ProjectMarket/actions/runs/40045091707):
все4 jobs PASS, 81 unit +90 integration =171 Python tests и48 Chromium scenarios;
Docker/HTTPS/restore PASS. Рабочий локальный Docker этой проверкой не обновлялся.

**Последнее продолжение, D45:** ответ «Продолжай» после прямого запроса разрешил
исправление общей очереди. Оно применено; повторное разрешение не требуется.
[Отчёт](task-results/PM-023-queue-fix.md):76 targeted tests +3 усиленных controls,
49 Edge scenarios PASS; независимый review без конкретных обходов/регрессий.
CI 40077334919 прошёл все 4 jobs. Предыдущие сообщения об ожидании разрешения исторические.
P1–P3 export/delete отвечены D46; Android/облако/L2 отложены;19/24, G05 ещё не наступила.
