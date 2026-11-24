# PM-023-PGDG · Восстановление сборки закреплённого libpq

24 ноября 2026 · P0 · issue #28. Независимое исправление после CI
45396108240 на a084681. Сборка остановилась: основной PGDG больше не содержит
`libpq5=18.6-1.pgdg12+2`. При этом установленный runtime исправен.

## Порядок и приёмка

- [x] Подтвердить наличие прежних libpq5/libpq-dev в официальном подписанном
  `bookworm-pgdg-archive`; сравнить libpq с установленными байтами.
- [x] Подключить архив к обычной и recipient replacement сборке.
  Сохранить exact version pins и проверку подписей прежним PGDG keyring.
- [ ] Пройти чистую сборку и реальные TLS/DB/modified-driver проверки CI.
- [ ] Записать результат и обновить issue/STATUS/CHANGELOG.

Это изменение доступности build inputs; оно не обновляет установленную
библиотеку и не пересоздаёт рабочие контейнеры. Счётчик 19/24, полная PM-023
и прежние отсрочки сохраняются.

Основание: [PostgreSQL FAQ об архиве старых версий](https://wiki.postgresql.org/wiki/Apt/FAQ#Where_are_older_versions_of_the_packages?),
[официальный формат DIST-pgdg-archive](https://apt-archive.postgresql.org/).
