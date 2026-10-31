# PM-023 · Go-зависимости Caddy

31 октября 2026 · продолжение D47. Полная PM-023 открыта;19/24, G05 planned.

## Охват и граница

Разобраны восемь Go-записей proxy750e506 из снимка30октября.
Статический этап до сборок: **0 confirmed, 0 not_actionable, 8 needs_review**.
[Реестр](assets/PM-023/dependencies-20261031/static-triage.json) сохраняет
каждый вход отдельно, evidence, gaps и ranks1–8. Применимого SECURITY.md для
deploy нет. Эксплуатация приложения не доказана.

Текущая граница: loopback8443 → Caddy `tls internal` → фиксированный api:8000;
admin выключен, конфигурацию Caddy пользователь/бот не задаёт. ACME server,
OIDC/JWK provisioners и HTML templates не включены. Smallstep участвует
в выдаче локального сертификата: InternalIssuer.Issue → CA.NewAuthority →
SignWithContext получает локальный X509 CSR, а не сетевой JWK/JWS.
Optional handlers остаются в штатной сборке; их активность не предполагается.

## Изменения

`deploy/Dockerfile.proxy` закрепляет chi5.4.0, go-jose/v4 4.1.7 и x/net0.62.0.
Сохранены Caddy2.11.7, Go1.26.10, builder/runtime digests, CGO_ENABLED=0,
APK packages, UID10001, read-only/cap_drop/no-new-privileges и каталоги CA.
CI проверяет новые версии в build-info; проверки curl/HTTP2 сохранены.

[Полный граф](assets/PM-023/dependencies-20261031/module-comparison.json)
содержит **девять** изменений: три pins и x/crypto0.58, x/sync0.24,
x/sys0.49, x/term0.47, x/text0.43, x/tools0.51. Это включает транзитивное
разрешение Go modules. `go mod verify` PASS. Список Caddy modules и APK manifests
совпали. [go-jose4.1.7](https://github.com/go-jose/go-jose/releases/tag/v4.1.7)
включает исправления, опубликованные30октября. Ветка v3 независима:
[фактическая цепочка](assets/PM-023/dependencies-20261031/jose-v3-chain.txt)
ведёт Smallstep authority → go.step.sm/crypto/jose → go-jose/v3.
Замена v3 на v4 через module replace не выполнялась: типы/API различаются.

## Проверки

Сборка и metadata PASS. Baseline builder воспроизвёл SHA-256 установленного
бинарника750e506; новый builder совпал с candidate image. В обоих import graphs
1017 packages; `golang.org/x/crypto/openpgp` и весь subtree **отсутствуют**.
Это контрдоказательство применимости [GO-2026-5932](https://pkg.go.dev/vuln/GO-2026-5932)
к данным linux/amd64 бинарникам, не исправление всей библиотеки x/crypto.
Первичный static-triage сохранён отдельно; raw finding не подавлен.

Временный proxy с новым CA: HTTPS readiness/database=ok, Web, HTTP/2,
отказ без доверенного CA (curl exit60), UID10001, BusyBox healthcheck и healthy
PASS. Второй временный proxy получил изолированную копию действующих data/config:
корневой сертификат совпал, HTTPS/HTTP2 PASS. Рабочий proxy этими проверками
не заменялся; оба временных контейнера остановлены.

9 tests в `tests/test_dependency_audit.py`, Ruff check/format, mypy92files PASS.
Независимый read-only review завершён: конкретных bypass/regression не найдено.
Его вывод не подменяет runtime-проверки и не закрывает оставшуюся ветку v3.
Первое чтение Go metadata без сети потребовало отсутствующие module info;
повтор с сетью прошёл. Docker cp отклонил копирование в read-only rootfs;
tar через stdin в tmpfs сохранил ограничения и прошёл. Сохранение evidence
в системный temp потребовало разрешения. Начальные сбои не считаются PASS.

## Повторный scanner

Trivy0.76.1, база **2026-10-31T13:09:00.83322165Z**. Два immutable image IDs
проверены последовательно одной базой; severity/ignore filters не добавлены.

| Proxy | Всего | Critical | High | Medium | Low | Unknown |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 750e506 | 8 | 0 | 2 | 3 | 0 | 3 |
| pm023-deps31 | 4 | 0 | 1 | 2 | 0 | 1 |

Отсутствуют четыре выбранных package/advisory matches:

- chi — [CVE-2026-114437](https://github.com/advisories/GHSA-j6qf-3m9c-vwj3),
  ClientIPFromXFF; наличие router не доказывает применение этого middleware.
- go-jose/v4 — [CVE-2026-116587](https://github.com/go-jose/go-jose/security/advisories/GHSA-mgcc-cww5-fp2q),
  проверка чрезмерного RSA private JWK.
- x/net — [CVE-2026-78661](https://pkg.go.dev/vuln/GO-2026-6860) и
  [CVE-2026-97045](https://pkg.go.dev/vuln/GO-2026-6866), HTML Parse/Render.

Остаются три go-jose/v3 записи116585/116586/116587 без исправленной версии
этой ветки и OpenPGP warning с указанным scoped контрдоказательством.
Reachability JOSE через действующий маршрут не доказана; эти записи нельзя
объявлять исправленными. API/DB/bot/locks этой итерацией не пересканировались;
общий счётчик не собирается из снимков разных дат.

## Доказательства и следующий шаг

[Runtime checks](assets/PM-023/dependencies-20261031/proxy-check.json),
[existing CA](assets/PM-023/dependencies-20261031/existing-ca-check.json),
[сравнительный audit](assets/PM-023/dependencies-20261031/proxy-audit.json.gz),
[candidate SBOM](assets/PM-023/dependencies-20261031/proxy.cdx.json.gz).
Рядом сохранены сжатые import graphs и build-info обоих бинарников.
Публичные материалы содержат технические версии/хеши и результаты;
секреты, пользовательские данные, CA keys и backup не публикуются.

Кандидат ожидает полного CI и установки с проверенным backup/restore.
Outcome **fixed** пока не заявлен до завершения этих проверок.
Следующий независимый разбор: bundled OpenSSL в psycopg и base findings;
затем notices и согласованные визуальные доработки/видео.
Android, облако и полный L2 остаются отложенными.
