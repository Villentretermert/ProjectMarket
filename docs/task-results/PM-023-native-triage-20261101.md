# PM-023 · разбор Kerberos/OpenLDAP после перехода на системные библиотеки

1 ноября 2026. Продолжение D47. Полная PM-023 открыта,19/24; G05 planned.

## Результат и охват

Разобраны **30 новых package/advisory записей,12 различных CVE** из предыдущего
API audit: **28 not_actionable,2 needs_review,0 confirmed**. Это не исправление
28 уязвимостей: для них установлено несовпадение конкретного затронутого пути
с поставляемыми компонентами/вызовами. Сканер сохраняет все276 записей; suppressions
и исключения не добавлялись. Остальные246 записей этим этапом не оценивались.

Исходная ревизия `e92861a0857daefd07b89c2a1f0e3ef8aa396230`;
API image `sha256:7a25ca664062d8f81018757e1cb542653536143971a6f5d73bcca9b10c17728b`.
Включены только API/maintenance/migrate на этом Linux image. Выводы не относятся
к PostgreSQL server image, Windows binary, хосту или произвольным расширениям образа.
Использованы сохранённый scanner package inventory, код и первичные источники.
Новые приложения, контейнеры, тесты и PoC на этапе статического разбора не запускались.

[Машиночитаемый результат](assets/PM-023/native-triage-20261101/triage.json)
содержит ровно один вердикт на каждую исходную запись, включая повторы одного CVE
для разных binary packages. [Сводка и проверка полноты](assets/PM-023/native-triage-20261101/summary.json).
High confidence:24 записи; medium:6 (четыре GSS encoding matches и два открытых LDAP).

## Почему 28 записей не требуют патча в этой границе

| CVE | Записей | Конкретное основание |
| --- | ---: | --- |
| [2026-107708](https://security-tracker.debian.org/tracker/CVE-2026-107708) | 4 | Уязвимый путь KDC/PAC; krb5kdc не входит в API image. |
| [2026-107778](https://security-tracker.debian.org/tracker/CVE-2026-107778) | 4 | Приём forwarded credentials в GSS acceptor; libpq работает инициатором. |
| [2018-5709](https://security-tracker.debian.org/tracker/CVE-2018-5709) | 4 | Kerberos administrative dump loader отсутствует; PostgreSQL backup не использует этот формат. |
| [2024-26458](https://security-tracker.debian.org/tracker/CVE-2024-26458) | 4 | Legacy pmap_rmtcall относится к libgssrpc4, которого нет в образе/пути клиента. |
| [2024-26461](https://security-tracker.debian.org/tracker/CVE-2024-26461) | 4 | Ошибочный путь encoding не вызывается корректными API inputs; libpq передаёт собственные ограниченные буферы. Confidence medium. |
| [2026-11850](https://security-tracker.debian.org/tracker/CVE-2026-11850) | 4 | Нужен LDAP KDB plugin в KDC/kadmind; сервер и plugin отсутствуют. |
| [2015-3276](https://security-tracker.debian.org/tracker/CVE-2015-3276) | 1 | Дефект NSS cipher parser; Debian OpenLDAP собран с GnuTLS. |
| [2017-14159](https://security-tracker.debian.org/tracker/CVE-2017-14159) | 1 | PID-file/slapd init-script; slapd не установлен и не запускается. |
| [2017-17740](https://security-tracker.debian.org/tracker/CVE-2017-17740) | 1 | nops/memberof server overlay; Debian nops не собирает, API не содержит slapd. |
| [2026-22185](https://security-tracker.debian.org/tracker/CVE-2026-22185) | 1 | mdb_load не собирается в Debian OpenLDAP, lmdb-utils в API отсутствует. |

Для GSS проверены обе ветки libpq18.6:
[authentication](https://github.com/postgres/postgres/blob/REL_18_6/src/interfaces/libpq/fe-auth.c#L103)
и [encryption](https://github.com/postgres/postgres/blob/REL_18_6/src/interfaces/libpq/fe-secure-gssapi.c#L616)
вызывают `gss_init_sec_context`. Они не предоставляют GSS acceptor API пользователю
MarkeTOB. [Upstream исправление 107778](https://github.com/krb5/krb5/commit/48afa9abb89ab2176bb20624d87d010b9984fc08)
обрабатывает несоответствие массивов в чтении KRB-CRED. Передача credentials со
стороны клиента не превращает его в принимающий сервис.

Для26458/26461 учтён [разбор сопровождающего MIT](https://mailman.mit.edu/pipermail/kerberos/2024-March/023095.html).
Это статическое контрдоказательство, а не результат эксплуатации либо runtime stress test.

## Две открытые записи

**Rank1 — CVE-2023-2953, libldap2.5.13+dfsg-5, needs_review/medium.**
[Debian](https://security-tracker.debian.org/tracker/CVE-2023-2953) оставляет Bookworm
affected/no-dsa. Upstream исправления касаются проверок ошибок выделения памяти в
[LDIF URL](https://github.com/openldap/openldap/commit/752d320cf96e46f24c0900f1a8f6af0a3fc3c4ce)
и [LDAP host parsing](https://github.com/openldap/openldap/commit/6563fab9e2feccb0a684d0398e78571d09fb808b).
В MarkeTOB нет LDIF import. Но optional
[libpq service lookup](https://github.com/postgres/postgres/blob/REL_18_6/src/interfaces/libpq/fe-connect.c#L5714)
может войти в libldap. Нужно установить точного caller, возможность вызова ошибки
allocation и влияние недоверенного ввода; этот путь не объявлен ни доказанным,
ни отсутствующим. Следующий шаг — целевой разбор libpq LDAP lookup и error path.

**Rank2 — CVE-2020-15719, libldap2.5.13+dfsg-5, needs_review/medium.**
Речь о выборе SAN/CN и обещанном правиле проверки TLS identity.
[Debian/upstream фиксируют спор RFC4513/RFC6125](https://security-tracker.debian.org/tracker/CVE-2020-15719).
Нужно установить поддерживаемый LDAP TLS consumer и его требуемую политику,
затем проверить соответствующую GnuTLS-ветку. Успешные PostgreSQL TLS тесты из
предыдущего этапа не проверяют TLS внутри libldap. Спор о стандартах не использован
как автоматическое основание закрыть запись.

## Границы доверия и код

Resolver для `apps/api` и `deploy` не нашёл применимого SECURITY.md. Основания
для границ — текущий код, Dockerfile и Compose; отсутствие policy не делает
находку безопасной само по себе. Нет новых продуктовых ограничений DSN.

- `deploy/Dockerfile`: PostgreSQL donor передаёт только ключ и список PGDG;
  PostgreSQL/Kerberos/LDAP servers из donor не копируются. В runtime устанавливается libpq5.
- `apps/api/src/marketob_api/config.py:71`: DSN поступает из Settings оператора.
  Боты и B2C HTTP-запросы не задают его через продуктовый API.
- `database.py:28,38,68`, `health.py:29`: pools, fallback и readiness — psycopg clients.
- `compose.yaml:37,63,82`: прямой PostgreSQL host/DSN; LDAP service file или GSS
  acceptor не настраивается. Это описывает default deployment, а не запрет альтернатив.

Сохранённый package inventory не содержит krb5-kdc, krb5-admin-server,
krb5-kdc-ldap, libgssrpc4, slapd, slapd-contrib, lmdb-utils, libnss3;
libgnutls30 присутствует. Этот факт относится к закреплённому образу, а не ко всем
будущим сборкам. При смене образа, consumers или настроек выводы нужно пересмотреть.

## Доставка результата

Изменены только пояснительная записка, JSON-результат, статус/журнал/issue.
Рабочая поставка68958f1, исходная БД и сертификат не менялись; повторная миграция,
backup или пересборка не требовались. Проверены полнота30/30, сохранение порядка
и повторов, уникальные ranks1–2; после экспорта проверяются JSON и локальные ссылки.
Предыдущий CI207 Python/54 Chromium остаётся доказательством предыдущего code commit,
а не новым тестированием этой статической оценки.

PM-023 открыта. Следующий приоритет: два LDAP proof gaps, затем остальные base
findings и license notices. Android/Google/облако/полный L2 остаются отложенными;
счётчик19/24 не изменён и новой контрольной точки не возникает.
