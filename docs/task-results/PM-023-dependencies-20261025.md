# PM-023 · Go-компоненты proxy и PostgreSQL

25 октября 2026 · продолжение по ответу S12 / решению D47.
Самостоятельная часть PM-023; полная приёмка задачи и внешнего пилота открыта.

## Изменение

В предыдущих образах найдены 32 исправляемые High/Critical записи о версиях:
6 в proxy и 26 в startup-helper `gosu` образа PostgreSQL. Статический разбор
подтвердил присутствие компонентов, но не доказал эксплуатацию каждого advisory.
Прокси принимает HTTP/TLS; gosu запускается entrypoint для смены пользователя
процесса PostgreSQL, не является сетевым обработчиком запросов к БД.

- `deploy/Dockerfile.proxy`: прежний Caddy 2.11.7 пересобран Go 1.26.10 с
  `golang.org/x/net` 0.60.0. Brotli обновлён до 1.2.1-r0. Wrapper сохраняет
  версию upstream Caddy в build info/SBOM; стандартные модули сохранены.
- `deploy/Dockerfile.db`: тот же PostgreSQL 18.6 Bookworm по digest, заменён
  только gosu 1.19, пересобранный Go 1.26.10. Архив исходников закреплён checksum,
  лицензия скопирована. Engine, entrypoint и layout существующего PGDATA сохранены.
- `compose.yaml` использует итоговый `marketob-db:<release>`; CI собирает его
  явно и проверяет версии бинарников и реальное согласование HTTP/2.
- `scripts/audit_dependencies.py` учитывает новый Dockerfile; runbooks обновлены.
  Bot API, схемы, миграции, локальная авторизация и интерфейс не изменены.

Официальные основания: [Go releases](https://go.dev/doc/devel/release),
[Go x509 advisory](https://pkg.go.dev/vuln/GO-2026-6809),
[HTTP/2 advisory](https://pkg.go.dev/vuln/GO-2026-6611),
[Caddy go.mod](https://github.com/caddyserver/caddy/blob/v2.11.7/go.mod),
[gosu 1.19](https://github.com/tianon/gosu/tree/1.19).

## Проверка версий

Оба варианта просканированы одной БД Trivy 0.76.1 от 2026-10-24T13:07:23Z.
Каждый образ разрешён в immutable ID; проверено совпадение ID в scanner JSON.
Ignore/suppression/ignore-unfixed не применялись.

| Компонент | Все записи до → после | Critical | High | Исправляемые High/Critical |
| --- | --- | --- | --- | --- |
| Proxy | 22 → 2 | 0 → 0 | 6 → 0 | 6 → 0 |
| PostgreSQL image | 474 → 415 | 4 → 3 | 96 → 71 | 26 → 0 |
| API / maintenance / migrate | 255 → 255 | 2 → 2 | 61 → 61 | 0 → 0 |

Все 32 выбранные пары package/advisory отсутствуют в новых образах. Всего
устранено 79 записей разных severity. Это совпадения версий с advisory,
не число доказанных атак. Для основных образов остаются **5 Critical и 132 High**;
образ отдельного бота повторяет API и не включён повторно в эту сумму.
В lock/build pins 57 Python и 3 Node packages известных advisory не найдено,
пропусков охвата нет. 56 Python metadata содержат declared license, одно unknown.

Доказательства: [сравнение, IDs и 32 записи](assets/PM-023/dependencies-20261025/comparison.json),
[полный audit JSON gzip](assets/PM-023/dependencies-20261025/audit.json.gz),
SBOM [proxy](assets/PM-023/dependencies-20261025/proxy.cdx.json.gz) и
[DB](assets/PM-023/dependencies-20261025/db.cdx.json.gz).
SHA-256 сжатых и исходных файлов сохранены в comparison.json.
Команды повторения: [dependency audit](../privacy/DEPENDENCY_AUDIT.md).

## Проверки совместимости

- Сборки обоих Dockerfile PASS. Caddy build-info: Go1.26.10 / Caddy2.11.7 /
  x/net0.60.0; gosu: 1.19 / Go1.26.10. Полный вывод list-modules старого и
  нового Caddy идентичен, 137 строк.
- `pytest tests/test_dependency_audit.py -q`: 9 PASS; Ruff check/format PASS;
  mypy: 92 файла PASS. Первые sandbox-запуски не могли создать tempdir;
  повтор с выделенным каталогом и разрешением исполнения прошёл.
- [CI40187348787](https://github.com/Villentretermert/ProjectMarket/actions/runs/40187348787)
  на `dac119f`: все 4 jobs PASS; 90 unit + 110 integration = 200 Python tests,
  54 Chromium scenarios. HTTPS/Secure cookie, реальный HTTP/2, свежий запуск и
  перезапуск БД, два бота, сбои/восстановление, backup/restore PASS.
  [Точные результаты](assets/PM-023/dependencies-20261025/ci-results.json).
  Один прежний warning Pydantic сохранён, он не является failure.
- Независимый read-only review не обнаружил конкретных обходов/регрессий;
  отдельно рассмотрены startup, права, PGDATA, direct callers и no-build flows.
- Установлен `dac119f`: четыре сервиса healthy, immutable IDs совпали с audit.
  API image переиспользован после проверки неизменности всех входов его сборки
  относительно 9afe3ec. Проверка локального HTTPS/Secure cookie/login/delete
  и HTTP/2 PASS; процесс PostgreSQL UID999, proxy UID10001.

Проверка безопасности здесь — замена известных уязвимых версий и повторный
scan. Exploit/DoS против рабочего сервера не выполнялся. Настройки доступа,
loopback, proxy UID10001, read-only, cap_drop и no-new-privileges сохранены.

## Локальная установка

Перед переключением остановлена запись и создан новый backup. Он восстановлен
в отдельном `marketob-pm023-deps25-restore`: все 29 таблиц и 10 sequences совпали.
После смены образа и запуска мигратора данные повторно сверены до возобновления
записи. Исходная `marketob_pm022` сохранена; engine остаётся PostgreSQL18.6.
Проверочный restore project остановлен, его volume сохранён.

[Поставка и image IDs](assets/PM-023/dependencies-20261025/local-delivery.json).
Приватные backup/прежний env находятся в `.local/pm023/dependency-delivery-03/`;
предыдущие images и копии сохранены. После новых записей нельзя откатывать старый
backup поверх текущей БД: [runbook](../setup/LOCAL_DELIVERY.md).

Edge на существующем demo-аккаунте: login → заполненный My Space → Live →
Data & privacy → личный JSON → logout PASS, page_errors=[]. Экспорт остаётся
приватным; проверены ограничение удаления владельца и отсутствие credentials
в выгрузке. [Результат](assets/PM-023/dependencies-20261025/deployed-browser.json)
и [фактический экран с demo-данными](assets/PM-023/dependencies-20261025/deployed-privacy.png).

Итог этой части: **fixed для 32 выбранных совпадений версий**. Подтверждены
замена компонентов, отсутствие этих записей в повторном audit и совместимость
легитимных сценариев. Это не закрытие всех findings и не доказательство
эксплуатируемости каждого исходного advisory.

## Что остаётся

P0: оценить оставшиеся системные Critical/High по реальным путям вызова и
distro advisory; отсутствие fixed version не доказывает безопасность.
В proxy остаются chi/v5 CVE-2026-114437 (Medium, fix5.4.0) и
x/crypto GO-2026-5932 (Unknown, fixed version не объявлена); они видны в audit.
Отдельно остаются license notices/source obligations и выбор лицензии проекта.
Android, облако, полный L2 отложены владельцем; 19/24 и G05 planned сохранены.
