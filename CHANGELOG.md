# Журнал изменений

## 2026-10-23 — PM-022: начата проверка эксплуатации и мощности

- Начата следующая разрешённая локальная задача: JSON-логи без содержимого запросов, отчёт метрик/alerts, ограничение очередей и истории, L2/burst на отдельном стенде.
- Принятый профиль: 100 ботов, 100 активных Web-клиентов, 1 000 сообщений/мин 30 минут; затем 3 000/мин 60 секунд. MAU не используется как concurrency.
- Работающий Docker-пилот сохраняется. Android/облако отложены. Приёмка PM-022 и G05 ещё не выполнены.
- Добавлены JSON-логи с allowlist полей и ротацией, CLI метрик/alerts, migration011 с учётом history bytes и floor очистки outbox, лимиты history/заявок/источников и backpressure. Старые квитанции не удаляются раньше срока ради новой записи.
- Диагностическая подготовка100 браузеров выявила стоимость открытия PostgreSQL-соединений на каждый запрос. Добавлены отдельные bounded pools для основных и вложенных quota/dispatch транзакций (psycopg-pool3.3.3), закрываемые вместе с API. Измерения после исправления ещё выполняются.
- После профилирования Message schema компилируется jsonschema-rs0.57.1 без изменения контракта. Повторная репетиция100 клиентов:2 000/2 000 отображены, live p95=1.988с/p99=2.144с, ingest HTTP p95=149мс. Unit75 PASS, backup/operations12 PASS, затронутые API/validator41 PASS; полный30мин L2 и CI пока не завершены.
- CI выявил Windows-only WinDLL в type-check Linux для измерителя ресурсов: заменён guard на sys.platform. Добавлен регрессионный тест восстановления worker из заполненного outbox с одновременно просроченной заявкой. API-поведение текущего L2 не меняется.

- Для L2 добавлена точная SQL-сверка ожидаемых пар bot/message ID после рестарта; результат полного прогона ещё ожидается. Подготовлен исходник G05, который отказывается создавать презентацию до принятого полного L2.

## 2026-10-23 — PM-021: локальная поставка и проверенное восстановление

- По прямому ответу владельца начата независимая Web/API/worker-поставка; Android остаётся отложенным.
- Реализованы Python backup/verify/restore, Compose local HTTPS, tags/DB switch, restart/resource limits, readiness по миграциям и отказ старого кода от более новой БД.
- Найден и использован существующий Docker внутри Ubuntu WSL; реальные build/start, TLS/Secure session, боты, backup/restore, HTTP replay и restart PASS. Исходная БД и посторонние контейнеры сохранены.
- Код c62c630: CI39948316689, 153 tests / 47 Chromium scenarios, все4 jobs PASS. Итог/снимки/runbooks в docs/task-results/PM-021.md. Завершено19/24, после G04:3/4; PM-022 → G05 после20. Android deferred.

## 2026-10-19 — PLAN-000: исходное планирование

- Зафиксированы рабочий регламент, отдельные вопросы владельцу и правила презентаций после каждых четырёх выполненных задач.
- Подготовлены 24 задачи пилота Android/Web/Docker и 4 задачи дальнейшего развития с зависимостями, приоритетами, результатами и критериями проверки.
- Описаны предложенные компоненты, сущности, API ботов, шаблоны интерфейсов и предварительные пользовательские сценарии.
- Создан демонстрационный макет; он не является работающим приложением.
- Учтены ответы Q01–Q17: название MarkeTOB, точный объём пилота, Google, self-service B2B, новости/товары/графики, заявки, обмен layout, новостной виджет, live/push, APK/Play и проектный предел 1 000 сообщений/мин.
- Выбор frontend, регион и бюджет пока открыты. Реализация PM-задач не начиналась.
- Проверки структуры плана и публикации фиксируются в `docs/PLAN_VALIDATION.md`.
- Созданы и сверены 35 GitHub Issues: 28 задач и 7 контрольных точек. Локальный реестр содержит прямые ссылки; скрипт синхронизации повторно не создаёт уже найденные задачи.
- Проверены структура зависимостей, локальные ссылки, Python/JavaScript syntax и отсутствие известных форматов секретов. Полная визуальная проверка макета ограничена доступом браузера к локальному серверу.

## 2026-10-21 — PM-001: требования локального пилота

- По указанию владельца первый запуск перенесён с облака на локальный компьютер; Docker-переносимость, Android/Web и APK/AAB сохранены. PM-021/024 и соответствующие решения обновлены.
- Добавлены 30 требований с проверяемыми сценариями, 16 пользовательских историй и карта исходных требований/ответов.
- Заданы инженерные SLO, три нагрузочных профиля, burst, начальные лимиты, retention и TTL; они явно отделены от результатов измерений и ответов владельца.
- Добавлена схема локального запуска с USB/LAN режимом, границами Google/Firebase и отдельными процессами ботов.
- Android-телефон доступен; Google/Firebase проект создаёт владелец по инструкции. Облачные регион и бюджет отложены.
- Проверки и фактический результат сохраняются в docs/task-results/PM-001.md.

## 2026-10-21 — PM-002: локальный режим и проверка Python-клиента (в работе)

- Последний ответ владельца отменяет необходимость Firebase сейчас: Google-вход и background push отложены, локальные аккаунты/сессии и live-события включены в задачи PM-006/018/019. Исторические ответы сохранены; текущие матрица, решения и описание обновлены.
- Добавлен Flet spike: каталог, новости, график/табличные значения, маршруты, сохранение избранного и явный demo-профиль. Это прототип с синтетическими данными, без готовой авторизации/backend.
- 14 тестов маршрутов и ограниченного формата локальных настроек прошли. Проверка браузера и сборок продолжается; Android/виджет пока не доказаны.
- Выявлены несовместимые зависимости динамического Flet (FastAPI/Starlette), неправильный socket-mode при view=None и ошибка Dart hook на Windows-пути SDK с пробелами. Исправлен HTTP-запуск; воспроизводимая Web-сборка проверяется отдельно.
- Инструкция Google/Firebase помечена отложенной. Подробные результаты будут в docs/task-results/PM-002.md; задача остаётся открытой.

## 2026-10-21 — PM-002: Web-приёмка и отложенный Android

- По прямому ответу владельца Android-сборка/USB отложены; SDK-лицензии не приняты. Текущий scope PM-002 изменён на Web+архитектуру, native gate явно перенесён в PM-019/020. Это не приёмка первоначального Android-критерия.
- Выбран HTML/CSS/JS Web runtime после практического сравнения с Flet. Backend/SDK/боты остаются Python. Добавлены ADR, инструкции двух spike, исходники Android-оболочки и настоящего AppWidget provider (ещё непроверенные).
- Web build из lock, npm audit, базовая доступность, 360px layout, избранное/chart persistence и reload при остановленном сервере проверены. Flet dynamic проверен; static runtime failures сохранены как ограничение.
- Скриншоты и фактические результаты находятся в docs/task-results/PM-002.md. Счётчик 2/4; дальше дизайн и контракт, затем G01.
- Исправлена публикация относительных Markdown-ссылок в GitHub issues: они теперь указывают на файлы репозитория.

## 2026-10-21 — PM-003: интерактивный дизайн (в работе)

- Создан отдельный адаптивный макет полного UX: Channels, каталог/новости/график, заявки, Studio, My Space, share/import и mockup виджета. Backend отсутствует; все операции и данные обозначены как демонстрационные.
- Добавлены условия Loading/Empty/Offline/Error/Revoked/Unavailable/Unsupported, явное время/источник, клавиатурный skip-link и touch targets.
- Сценарий импорта разделяет layout и grants: в preview Carol не получает закрытые данные Bob. Дизайн-имитация не считается серверной проверкой прав.
- Браузерная приёмка и визуальные доказательства выполняются до закрытия PM-003.

## 2026-10-21 · PM-003 завершена

Английский интерактивный UX: Channels, Studio, My Space, обмен оформлением, заявка, локальный вход и макет виджета. Проверены desktop/mobile сценарии, 12 цветовых пар, клавиатура и каталог 320 px. Исправлены повторная заявка и отображение закрытого источника. Сценарии и доказательства сохранены; API, native widget и настоящая аутентификация ещё не реализованы.

## 2026-10-21 · PM-004 начата

Уточняются схемы OpenAPI/JSON Schema и английский протокол HTTP-ботов. Реального API пока нет; сценарии надёжности проверяются на контрактной модели.

## 2026-10-21 · PM-004 завершена

Зафиксированы 44 операции и 64 схемы API 1.0, английский протокол/quickstart, 20 примеров и Python-модель ошибок/повторов/доставки. OpenAPI валиден, 25 тестов прошли. Ключи, права и данные исключены из layout; ACK отделён от результата. Это контракт, не запущенный сервер. Счётчик 4/4: далее обязательная презентация G01 и отдельные вопросы.

## 2026-10-21 · G01 представлена, ожидаются ответы

Сохранены PPTX (9 редактируемых слайдов), PDF-копия, разбор кода/сущностей/системы и следующие PM-005–008. Все слайды и страницы визуально просмотрены; PDF собран из отрисовок после ошибки штатного font export. Заданы 12 отдельных вопросов. Ответ 1 принят: сохранить текущую плотность UI. G01 остаётся открытой, PM-005 не начата.

G01: .gitattributes фиксирует PDF/PPTX/изображения как binary, чтобы Git не менял окончания строк экспортированных файлов.

## 2026-10-22 — G01: переход к PM-005

- Сохранено явное указание владельца перейти к следующей задаче; G01 закрыта согласно пункту 7 регламента. Неотвеченные вопросы сохранены отдельно от рабочих допущений.
- PM-005 начата: воспроизводимый FastAPI-каркас, конфигурация, health, локальный Compose и реальные CI-проверки. Android и облачные сервисы остаются отложенными.

## 2026-10-22 — PM-005: каркас и локальное окружение (проверка)

- Создан uv workspace: Python 3.14.7, FastAPI, настройки без обязательных секретов, CLI с loopback по умолчанию. Health разделяет живой процесс и готовность PostgreSQL, ошибки не раскрывают DSN.
- PM-004 перенесён в packages/contracts без изменения схем/протокола; обновлены ссылки. Для клиента, SDK и ботов зафиксированы отдельные границы; HTTP-пробник работает отдельным процессом.
- Добавлены закреплённые Dockerfile/Compose, случайный локальный пароль без перезаписи .env, volume PostgreSQL, изоляция runtime от исходных секретов и dev-пакетов. Docker локально отсутствует; контейнерный smoke выполняется в CI.
- Добавлены реальные GitHub Actions для Windows/Linux: lint, format, strict typing, unit/contract tests, запуск чистого процесса; отдельная сборка Compose и проверка отказа/восстановления БД.
- Локально: 39 passed, 1 optional PostgreSQL test skipped; lint и typing проходят. Итоговые CI/startup-доказательства будут записаны в результат PM-005 после выполнения.

- Первый Linux CI подтвердил Docker/PostgreSQL, но обнаружил отсутствие корня репозитория в pytest console-entrypoint при импорте scripts.dev_env. Явный pytest pythonpath исправляет одинаковый запуск через CLI/модуль; команда CI локально повторена: 39 passed.

## 2026-10-22 — PM-005: приёмка

- 39 unit/contract tests прошли локально и в CI на Windows/Linux; lint, format и strict typing PASS. Чистый git archive без .env/venv устанавливается по lockfile и запускает HTTP.
- Linux Docker CI собрал минимальный непривилегированный образ, подтвердил PostgreSQL readiness, отказ/восстановление БД и restart API. Локальная установка Docker не выполнялась. Отчёт, выдержки и ссылка CI сохранены в результате задачи.
- Обновлены STATUS/ROADMAP/README, инструкция запуска, GitHub task и счётчик: 5/24, 1/4 до G02. AGENTS отсылает к актуальному счётчику вместо устаревшего нуля.
- По новому указанию владельца далее выполняются PM-006–008 по очереди; затем G02.

## 2026-10-22 — PM-006: локальная identity (в работе)

- Начаты миграции PostgreSQL для пользователей, сессий, личных B2B организаций, членства и grants; локальная регистрация, вход и отзыв сессии. Запланированы реальные проверки двух аккаунтов, CSRF/origin, rate limit и разграничения прав.

- Реализованы Argon2id, 24-часовые opaque sessions, origin/CSRF, общий безопасный Error envelope, ограниченный JSON transport, PostgreSQL rate windows, личный B2B workspace и owner membership, exact username lookup, grants и подписанные курсоры. Удаление аккаунта реализовано как явно описанная деактивация.
- Миграции SQL транзакционные, с checksum/advisory lock; Compose запускает отдельный migrate service. Контракт 1.0.1 расширен аддитивно до 67 схем/48 плановых операций; runtime не объявляет будущие маршруты готовыми.
- Подготовлена отдельная PostgreSQL 18.6 в .local без системной службы. Кириллица в пути initdb обходится коротким Windows-путём. 58 тестов и настоящий HTTP identity smoke локально прошли; CI-проверка обновлённого контейнера продолжается.

## 2026-10-22 · PM-006 принято / PM-007 начало

PM-006: все четыре CI jobs PASS на `94a2cf3`, локально 58 tests и HTTP smoke PASS; issue закрывается с доказательствами. PM-007: начаты registry, bootstrap/operational credentials и серверные права. Зависимость PM-006 проверена; новый пользовательский UI пока не подключён.

## 2026-10-22 · PM-007 registry и ключи

Реализованы registry, одноразовый bootstrap, scoped operational keys, rotation/revoke, last_seen, signed inventory и квоты. Контракт 1.0.2 добавляет два read endpoints без изменения существующих ответов. 64 локальных теста PASS, включая двойной обмен на PostgreSQL; HTTP smoke расширен для Docker. CI приёмка впереди.

## 2026-10-22 · PM-008 приём и хранение

Добавлены черновик канала, schema-validated text/data/event/delete, idempotency/versions/tombstones, атомарные receipt/history/outbox и token buckets. Retention worker включён в Compose. 9 новых PostgreSQL сценариев PASS; 100 реальных HTTP сообщений за 3.384s, p95 222.53ms; restart/replay/revoke PASS. Устаревший тест отсутствия messages обновлён. Длительная нагрузка и UI пока не проверяются; CI приёмка впереди.

## 2026-10-22 · PM-007 принято

Все четыре CI jobs PASS на `ab48d25`; issue закрывается с результатами lifecycle/изолированных ключей/конкурентного обмена. Следующая PM-008 реализуется на проверенной зависимости.

## 2026-10-22 · PM-008 проверка запуска maintenance

Первый CI: Python Windows/Linux и PostgreSQL PASS, Docker остановился на Compose --wait без healthcheck нового maintenance-сервиса. Добавлен heartbeat последнего успешного прохода и отдельная --health проверка (130 секунд). Failed database pass не обновляет heartbeat. Docker прогон повторяется; функциональные 73 tests локально PASS.

## 2026-10-22 · PM-008 состав Docker-образа

После успешного healthcheck и HTTP identity/bot smoke проверка минимального образа обнаружила лишнюю reference model. Dockerfile теперь явно копирует только runtime API и два файла schema package; .dockerignore дополнительно исключает остальные contract sources. В CI у каждого packaging assert собственная причина.

## 2026-10-22 · PM-008 принято / G02

Финальный `6f62ac5`: все четыре CI jobs PASS, 47 unit/contract + 26 PostgreSQL tests, Docker HTTP burst/restart/revoke/retention. Локально 73 tests PASS и проверка heartbeat PASS. PM-008 закрывается. G02: 10 проверенных слайдов PPTX, PDF-копия для чтения, системный дизайн, пояснения к коду и 12 отдельных вопросов. Ответы ожидаются; PM-009 не начата. STATUS/ROADMAP/README и checkpoint-счётчик обновлены: 8/24, 4/4 после G01.

## 2026-10-22 · G02 / PM-009 — ответы и начало следующего блока

Сохранены 12 ответов владельца, закрыта G02, разрешены PM-009–012. Командные роли включены в PM-014 с обязательной проверкой PM-023. Уточнены RSS, каталог, Selected users, Request purchase/quantity=1 и напоминания ключей. History worker изменён с 7 на 30 дней; тест границ 29/31 день подготовлен, результат проверки будет в PM-009. Android/облако остаются отложенными.

## 2026-10-22 · PM-009 — версии, публикация и чтение каналов

Добавлены migration 004, immutable channel_versions, отдельная draft visibility, publish/preview/rollback, owner inventories и consumer snapshot. ETag проверяется после прав, запросы no-store; удалённые/несовместимые и неиспользуемые источники исключены. Контракт 1.0.3, руководство CHANNELS.md, ADR-0007 и HTTP smoke в Docker CI. Первый прогон: 78 PASS/2 FAIL (ожидание кода отключённого канала и описание поля схемы), оба исправлены. Итоговые результаты будут в PM-009.

## 2026-10-22 · PM-009 — приёмка

81 локальный тест, HTTP lifecycle, Ruff/format/mypy/совместимость пакетов PASS. Commit e38dc57: CI 39825150008, все 4 jobs PASS, включая контейнерный HTTP и восстановление БД. Сохранены доказательства, PM-009 принята, счётчик 9/24 (1/4 после G02). Далее PM-010.

## 2026-10-22 · PM-010 — начало заявок

Начата реализация атомарных action/event/outbox, отдельных GET/ACK/result, durable idempotency и обработки отзыва/таймаутов. G02: только Request purchase, quantity=1, без оплаты/корзины. Дизайн доставки сохраняет события до ACK и незавершённые заявки до результата.

## 2026-10-22 · PM-010 — delivery и конкурентный отзыв

Добавлены migration 005, actions.py/request_state.py, durable события/квитанции результатов, async long poll без удержания соединений, timeout/retention worker, hooks для grant/visibility/account/bot/channel revocation. Проверен порядок organization→bot→channel→request с учётом FK. Добавлены API guide/ADR, PostgreSQL tests и двухфазный HTTP restart smoke; CI auth quota 100 только для синтетического общего IP, normal default 10 сохранён. Первые 8 action tests PASS; полный набор проверяется.

## 2026-10-22 · PM-010 — проверка grant/deactivation

После полного локального набора 94 PASS и CI c49a6c4 (39828023837, success) при чтении кода найден потенциально обратный порядок блокировок grant и деактивации пользователя с pending-заявкой. Grant теперь проверяет target user до channel. Добавлен race test; связанные actions/identity/channels 32 PASS, Ruff/format/mypy PASS. Следующий CI проверит финальную правку.

## 2026-10-22 · PM-010 — приёмка

Финальный commit c9396c5: CI 39828592091 completed/success, 48 integration + 47 unit/contract, все 4 jobs PASS. Контейнерный HTTP/DB outage/restart сохраняет pending/ACKed заявки и дедупликацию результатов. Доказательства сохранены, PM-010 принята: 10/24, 2/4 после G02. Далее PM-011 SDK и два бота.

## 2026-10-22 · PM-011 — SDK и пилотные боты

Начаты отдельный Python HTTP SDK и два процесса ботов без доступа к БД платформы. План: журнал SQLite для повторов/ACK/result, синтетический каталог повседневных товаров, настраиваемый RSS (NASA проверен HTTP 200, 10 записей) и offline fixture, отдельный Dockerfile/profile.

## 2026-10-22 — PM-011: SDK и два независимых бота

- Добавлен typed HTTP SDK с bounded JSON/schema validation, retries 429/503/transport с прежним body, запретом redirects и безопасными ошибками. Bootstrap exchange не повторяется автоматически.
- Каталог повседневных товаров и RSS/Atom бот используют собственные SQLite journals; inbox до ACK, demo ledger до result, recovery без повторного эффекта. RSS имеет offline fixture, безопасный XML parser и график окна публикаций.
- Добавлены отдельный bot Dockerfile/Compose profile, owner provisioning через HTTP, process/container smoke и Telegram adapter. DB credentials не передаются ботам; API Docker build учитывает новые workspace packages.
- Локально 117 тестов PASS (102.18s), в том числе 22 SDK/journal/XML; реальные два процесса PASS: 4 товара, 5 новостей+график, key isolation, private access, confirmed/failed и restart. Ruff/mypy/traceability PASS. Один предупреждающий Pydantic alias warning в конкурентном тесте; функциональных отказов нет. Контейнерная проверка ожидает CI.

- PM-011 CI выявил Linux-only mypy ошибку обращения к Windows CREATE_NO_WINDOW; заменено переносимым getattr. Локально mypy --platform linux и Windows, Ruff PASS.

- PM-011 принята: code 49110ee, CI 39833237430, все 4 jobs PASS; 117 tests и оба Python/Docker smoke PASS. Счётчик 11/24, после G02 3/4.

## 2026-10-22 — PM-012: интеграционный стенд (в работе)

- Начата воспроизводимая проверка API/maintenance/bot process crash и открытого потока 1000 сообщений/мин с отдельной тестовой схемой PostgreSQL. Полный L2 30 минут/100 UI clients и live latency остаются PM-018/022; здесь baseline API и сохранность.

- Устранены устаревшие формулировки Google-входа в планах PM-013/015: текущий пилот использует согласованный локальный вход. CHECKPOINTS приведён к принятым ответам G02; scope будущих задач не расширен.

- PM-012 baseline PASS: 3000/3000 за180.139с, 100 bot identities, 10 read sessions, 1549/1549 чтений, p95 ingest295.02мс/read253.76мс. После API restart все3000 receipt/outbox и100 latest revisions сохранены. CI выявил неверное ожидание503 на искусственный SQL trigger error; контрактно верный ответ500/internal_error, ожидание исправлено.

- PM-012 принята: b3c00f4/CI39835253441,4 jobs PASS,117 tests, fault lab и local/CI paced load PASS. Завершено12/24, после G02 4/4. Начата G03, дальнейшие PM-задачи ждут обсуждения.

## 2026-10-22 — G03: презентация результатов

- Подготовлены 10 слайдов PPTX, PDF для просмотра, Markdown с разбором кода/сущностей и системная схема. Показаны готовые PM-009–012 и отложенные UI/Android/live/backup/L2 проверки.
- Проверены все слайды и PDF-страницы, исправлены подписи стрелок. PPTX содержит 5 редактируемых таблиц и 2 схемы; PDF растровый. Нативный PowerPoint не открывался.
- Подготовлены 13 отдельных вопросов по ролям, поведению Web и следующему блоку. G03 остаётся открытой до ответов либо явного разрешения продолжить.

- G03 показана владельцу; 13 вопросов отправлены отдельными карточками. Ответов пока нет, следующие задачи не начаты.

## 2026-10-22 · G03 / PM-013–016

Сохранены все 13 ответов, закрыта G03, начата PM-013. Уточнены роли, начальный экран/виды блоков, подтверждение заявки, ручное избранное, autosave/Undo и общие новости. Счётчик остаётся 12/24: новые задачи ещё не приняты.

## 2026-10-22 · PM-013 · Working Web

Web /app/ включён в Python API/wheel/Docker: local login, каналы, news/product/chart, подтверждение Request purchase, реальные статусы и восстановление того же запроса после потери ответа. Безопасный текст/HTTPS, CSP, loading/empty/error/offline, адаптивность и keyboard. BBC World вместо NASA по G03, list/article по умолчанию. 118 Python/PG tests PASS; 14 браузерных сценариев Edge PASS, 360/1440px, SQL проверка отсутствия дубля. CI Linux/Docker/Chromium ещё ожидается. Studio/My Space пока явно отмечены до следующих задач.

## 2026-10-22 · PM-013 accepted / PM-014 started

CI 39846617703 на 79a3f979: Ubuntu/Windows, PostgreSQL/Chromium и Docker PASS. 118 distinct Python/PG tests, 14 browser scenarios. Скриншоты пересняты после загрузки sidebar; повторный Edge PASS. PM-013 закрыта, счётчик 13/24, после G03 1/4. Начата PM-014 по разрешению полного блока.

## 2026-10-22 · PM-014 · Studio implementation

Добавлена миграция 006 и серверная матрица Owner/Admin/Editor: workspace membership, точный username, защита единственного владельца, изоляция workspace/cursors, немедленный отзыв после commit. Editor публикует/откатывает оформление; audience и grants ограничены Owner/Admin. Контракт 1.0.4 добавляет workspace/member/audience API без изменения wire 1.0. Studio подключает bots/keys/pages/team, preview/publication/rollback и expiry reminders. Проверки и приёмка выполняются; PM-014 ещё открыта.

## 2026-10-22 · PM-014 · Local validation

125 Python/PG/contract tests PASS (184.76s), 24 Edge UI scenarios PASS. Проверены конкурирующий отзыв, обе стадии заявки, новая сессия, audience draft vs published и все три роли. Исправлены переход после выдачи credential, доступные имена select и вертикальное размещение expiry banner. При 429 UI показывает Retry-After; обычные read quotas сохранены. Документация и реальные экраны сохранены; CI ещё ожидается.

## 2026-10-22 · PM-015 implementation

Начата разрешённая PM-015: избранное с синхронизацией аккаунта, ручным порядком и маркерами прочитанных ревизий. Макет и политика скрытия недоступных данных показаны до реализации. Максимум 100 каналов; конкурентная перестановка проверяет версию списка. PM-014 пока ожидает финальный браузерный job CI.
## 2026-10-22 · PM-014/015 CI setup

CI 39851029904: три jobs PASS; integration прошёл PostgreSQL/backend checks, но timeout во время загрузки apt fonts с azure.archive.ubuntu.com до браузерного прогона. Playwright теперь скачивает Chromium без повторной apt-установки имеющихся на hosted Ubuntu библиотек. Браузерные проверки сохранены полностью; следующий CI проверит runtime. Локально PM-015: 29 Edge сценариев PASS.
## 2026-10-22 · PM-015 local validation

Избранное реализовано в PostgreSQL и Web; контракт 1.0.5, 84 schemas / 61 operations. 130 Python/contract/PG tests PASS (200,67с), 29 Edge scenarios PASS; Ruff/mypy Windows/Linux PASS. Три фактических экрана проверены. Сначала тест выявил неподключённые валидаторы новых запросов; исправлено. Описания полей схем дополнены и весь набор повторно пройден. Приёмка ожидает CI.

## 2026-10-22 · PM-014 accepted

CI 39853394634 на b4c26cb прошёл все 4 jobs: 125 distinct tests, 24 Chromium scenarios, backend fault/load и Docker. PM-014 закрыта; 14/24, после G03 2/4. PM-015 code 70d31e0 подготовлен к CI после 130 локальных tests и 29 Edge scenarios.

## 2026-10-22 · PM-016 started

На основе завершённой реализации PM-015 (130 локальных tests/29 Edge PASS; CI в финальной проверке) начат My Space. Макет показан заранее и сохранён в docs/design/MY_SPACE.md: ссылки на опубликованные блоки, автосохранение/Undo, конфликт версий, 20 страниц/50 блоков/20 Undo шагов как инженерные ограничения пилота.

## 2026-10-22 · PM-015 accepted

CI 39854053654 на aa9e792: все 4 jobs PASS, 130 distinct tests, 29 Chromium scenarios и Docker/backend. PM-015 закрыта; 15/24, после G03 3/4. PM-016 выполняется по разрешению всего блока.

## 2026-10-22 · PM-016: личные страницы и проверка источников

Добавлены миграция 008, CRUD/snapshot My Space, отдельный layout, compatible views, autosave/Undo и восстановление после потерянного ответа. Текущие права проверяются для каждого блока; исходные B2B страницы не меняются. Контракт 1.0.6, 86 схем/62 specified operations. 36 Edge scenarios PASS; финальная серверная/CI проверка продолжается. Визуально исправлены текст новости при compact density и мобильные оси графика. Обмен, idle updates, Android и облако пока не реализованы/отложены.

## 2026-10-22 · PM-016 accepted / G04

PM-016 принята на f2dcde7: CI 39858054474 все 4 jobs PASS, 137 distinct tests, 36 Chromium scenarios; Edge и 137 локальных tests PASS. Завершён блок PM-013–016, счётчик 16/24. G04 содержит PPTX/PDF, фактические экраны, матрицу ролей, разбор компонентов/сущностей и готовности, следующие задачи и 13 отдельных вопросов. Ответы ожидаются; PM-017 не начинается. Android/облако остаются отложены.

## 2026-10-23 · G04 / PM-017 start

Принято указание «Продолжай»; G04 закрыта с явным перечнем рабочих допущений, PM-017 начата. PM-018 разрешена следующей; Android/облако сохраняют отсрочку. Счётчик остаётся 16/24 до приёмки.

## 2026-10-23 · PM-017 implementation

Добавлены migration009, Share/Import API/UI, сохранение назначения ссылки при входе, preview с проверкой прав, независимые копии, version guard, replay, сроки и отзыв. Контракт1.0.7 (87схем/63operations). Пять новых PG tests PASS; полная регрессия/визуальная проверка продолжаются. Ссылка локального сервера не предоставляет другу сетевой доступ автоматически.
# 2026-10-23 · PM-017 final verification

Import fixes the code and preview while an uncertain request is retried, preserving
one idempotent intent. Linux CI exposed a My Space title-edit race: a late source
picker repaint could overwrite text before blur. Repaints now preserve the focused
title. Final browser and CI verification follows; the initial Linux browser run failed.


## 2026-10-23 · PM-017 accepted / PM-018

PM-017 принята: 142 tests, 41 browser scenarios; [final CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39924166312) all four PASS. Счётчик17/24, послеG04 1/4. PM-018 начата: предварительный макет, polling2s, delivery order after commit, session cursors/preferences; runtime проверяется далее.
# 2026-10-23 · PM-018 implementation

Migration010/updates.py add post-commit delivery ordering, rolling session cursor,
bounded scans, current authorization, own preferences and actor-only request hints.
Grant/team restoration emits refresh hints. Contract1.0.8:87schemas/64operations.
Web polls every2s, resyncs after failure/expiry, clears inaccessible sources and
preserves title/layout/Undo. Events controls wait for saved preferences before
allowing edits. Automatic request status uses GET. Added real PG/browser scenarios
and ten-browser L1 measurement; final acceptance evidence follows.

## 2026-10-23 · PM-018 verification refinements

Fixed Events loading controls and aligned checkbox labels; Live uses a calm green
status. Added browser replay-dedup/offline timing and an optional focused live suite,
plus persisted-cursor/concurrent dispatcher coverage for personal-page interests.
PM-023 explicitly tracks outbox/preferences cleanup and cursor floor after retention.

## 2026-10-23 · PM-018 browser synchronization

The Events regression test now waits for the persisted checked state before
unchecking. Playwright may skip uncheck on the initial disabled/empty control;
production controls already remain disabled until preferences load. Initial Linux
run exposed this test race; the final run verifies the actual change to events[].
## 2026-10-23 · PM-018 repeated authorization invalidation

Edge exposed a fast revoke/restore/revoke race: an independent picker snapshot could
restore DOM content while a repeated revoke hint was deduplicated. Every denial now
clears affected content even for repeated hints; dedup only suppresses redundant
network refresh/notifications. Picker failures paint the cleared state immediately,
before changing request generations. Focused and full browser checks are repeated.

## 2026-10-23 · PM-018 sidebar revocation

Access denial now also replaces the matching sidebar title immediately, before
snapshot refresh. Browser acceptance waits for both cleared content and sidebar
metadata before capturing the revoked state.


## 2026-10-23 · PM-018 accepted

[Final CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39929710247) on5c20d9f: all4 jobs PASS,147 tests / 47 Chromium scenarios. Edge47 PASS. L1 10bots/10clients/100msg/min/900s:1500/1500 rendered, p95 2467ms/p99 2625ms, no HTTP/page errors. Reconnect2371ms, offline840ms. Reports/screens/API/ADR saved, counters18/24 and G04 2/4. Android/background/cloud remain deferred; no G05 until four completions.
