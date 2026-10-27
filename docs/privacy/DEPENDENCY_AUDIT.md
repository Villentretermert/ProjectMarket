# Повторяемая проверка зависимостей

Из корня ProjectMarket; Python3.14+, Trivy0.76.1 и доступ к Docker daemon.
В Windows используется установленная Ubuntu WSL; в Linux опустите `--wsl Ubuntu`.
Скрипт не устанавливает/обновляет зависимости приложения, не запускает containers,
не читает пользовательские volumes и не использует GitHub credentials.
Публичный PyPI получает только имена/версии пакетов для metadata; Trivy загружает
свою vulnerability DB. Кеш и полный log остаются в `.local`.

## Подготовка Trivy

Получите Linux amd64 archive из [официального релиза0.76.1](https://github.com/aquasecurity/trivy/releases/tag/v0.76.1),
сравните SHA-256 с опубликованным checksums до запуска. Использованный archive:
`trivy_0.76.1_Linux-64bit.tar.gz`, SHA-256
`c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0`.
Это проверка checksum через HTTPS, не заявление о проверке Sigstore provenance.
Поместите executable в `.local/tools/trivy-0.76.1/trivy`.

Пример для подготовленных локальных образов (тег candidate не означает установленный релиз):

```powershell
.venv-dev/Scripts/python.exe -m scripts.audit_dependencies --trivy .local/tools/trivy-0.76.1/trivy --wsl Ubuntu --output .local/audit-unique-name --image marketob-api:d53232e --image marketob-proxy:d53232e --image marketob-bot:d53232e --image marketob-db:d53232e
```

`--image` повторяется для каждого **существующего локального образа**; выберите
теги проверяемой сборки. Без этого параметра проверяются только lock/build pins.
Сканируйте итоговый `marketob-db`, а не только upstream PostgreSQL: начиная с
25 октября `deploy/Dockerfile.db` пересобирает его startup-helper `gosu`.
`--output` обязан быть новым каталогом внутри repo: старый результат не перезаписывается.
Сканируется ID, полученный `docker image inspect`; совпадение ID проверяется в JSON.
Не выполняйте команды runbook с новым Compose на рабочем volume до backup/restore.

## Результат

- `report.json`: UTC, Git HEAD, hashes входных файлов, версия/дата БД сканера,
  имена/версии всех найденных компонентов, advisory, declared licenses и пропуски.
  HEAD — base commit; входные hashes отражают staged working tree, в том числе
  незакоммиченные изменения. Git HEAD не подменяет идентичность образа.
- `image-N.cdx.json`: SBOM соответствующего image в порядке `--image`.
- `*.raw.json`, `scanner.log`: исходные scanner evidence; перед публикацией проверить
  содержимое. Существующие public assets — явно отобранные projections и image SBOM.
- Exit0 — для проверенного охвата не найдено известных advisory; exit1 — найдены;
  exit2 / INCOMPLETE — проверка неполна. Ни один код не означает полную security или
  лицензионную приёмку. Unknown license сохраняется для ручного разбора.

Сканирование не скрывает unfixed/LOW/UNKNOWN, не использует `.trivyignore` и не
фильтрует findings для красивого счётчика. Для оценки влияния нужны отдельные
сведения о reachable API paths и официальные distro/upstream advisories.
Старый отчёт не гарантирует отсутствие CVE, опубликованных позднее.

[Trivy Python coverage](https://www.trivy.dev/docs/latest/guide/coverage/language/python/):
uv license metadata отсутствует, поэтому Python licenses отдельно запрашиваются
через [version-specific PyPI JSON](https://docs.pypi.org/api/json/).
[Node coverage](https://www.trivy.dev/docs/latest/guide/coverage/language/nodejs/)
и [container scanning](https://trivy.dev/docs/latest/target/container_image/)
определяют границы остальных проверок. Это inventory declared metadata, не
юридическое заключение о совместимости или выполненных obligations.
