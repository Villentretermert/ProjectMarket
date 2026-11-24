# Автономная пересборка Caddy и gosu

24 ноября 2026 · PM-023-GOBUILD. Проверка двух Go-программ из schema-20261109.

Рецепт `scripts/go_rebuild.py` использует [Go source kit](GO_SOURCES.md),
проверяет его внешнюю квитанцию и собирает gosu/Caddy из сохранённых файлов.
Он сравнивает бинарники с установленными, затем проверяет смену UID/GID,
HTTPS/HTTP2, отказ при недоверенном CA и несовпадающем имени сертификата.
Результат остаётся в отдельном каталоге; команды установки в пилот нет.

## Подготовка

Нужны текущий репозиторий с этим рецептом, Python 3.11+ (только stdlib), Linux
Docker/WSL и проверенный `kit-03`. До отключения сети получите точный образ:

```powershell
wsl -d Ubuntu --exec docker pull --platform linux/amd64 golang:1.26.10-alpine3.23@sha256:0525c952defebc693cdaf62cdf43afa32be5a7f377e99260642ea19c240c708e
```

Скачивание образа и исходного комплекта — отдельная сетевая подготовка.
Для полностью отключённого получателя образ можно заранее передать через
`docker save/load`; готовый переносимый Docker kit прежней поставки этот
дополнительный compiler image не содержит. Сам компилятор здесь не собирается.
Резервируйте несколько ГБ Docker disk space для исходников/кешей компиляции.
Контейнер ограничен двумя CPU, 3 GiB памяти и 256 процессами; это сборка,
не нагрузочная приёмка продукта. На хостах без swap accounting Docker
предупреждает, что swap limit не поддерживается.

## Запуск

Из корня репозитория в PowerShell, выбирая новый output:

```powershell
.venv-dev/Scripts/python.exe -m scripts.go_rebuild --kit .local/pm023/go-20261124/kit-03 --output .local/go-rebuild-new --wsl Ubuntu
```

На Linux:

```sh
python -m scripts.go_rebuild --kit /path/to/kit-03 --output .local/go-rebuild-new
```

Итог `result.json` содержит hashes, toolchain image ID, исходную квитанцию,
подготовленный tar, наблюдаемую сеть/окружение и результаты функций.
`binaries/db` — gosu, `binaries/proxy` — Caddy. `tls-probe` — только тестовый
клиент. Остальные файлы — наблюдения сборки и диагностические логи.
`INCOMPLETE.txt` означает непринятый запуск; существующие результаты не
перезаписываются. Рабочие БД, volumes, контейнеры и CA не подключаются.

## Что именно проверяется

Сначала проверяются все bytes/h1 source kit. Из него формируется
детерминированный tar с `cache/download/*.zip`, `*.mod`, `*.ziphash`, main и
go.mod/go.sum. `.ziphash` берётся из уже проверенного h1; `.info` не выдумывается.
Для этих двух закреплённых сборок `.info` не понадобились.

Каждый запуск получает новый пустой Docker volume. В него распаковывается
только подготовленный tar; компилированных пакетов внутри нет. В начале
проверяются пустота тома и отсутствие compiler/module cache. После подготовки
Go сам распаковывает проверенные module ZIP; `go mod verify` подтверждает
содержимое. Gosu и затем Caddy используют один новый compiler cache этого
запуска. `GOPROXY=off`, `GOSUMDB=off`, `GOTOOLCHAIN=local`, `GOWORK=off`;
`go build -mod=readonly -trimpath`, CGO выключен. go.mod/go.sum после сборки
должны совпасть с исходными. Временные объекты компилятора находятся в
`GOTMPDIR=/work/tmp` на дисковом томе.

На Linux новый каталог `output/binaries` имеет mode 0775, compiler container получает
его группу владельца. Это позволяет писать в bind mount при cap_drop=ALL
без DAC_OVERRIDE и без разрешения записи всем пользователям. Исходные
каталоги/рабочие данные не получают новых прав.

Все три контейнера запускаются с `--network none --pull never --read-only`.
В сборочном контейнере отдельно наблюдаются интерфейс `lo` и Go environment.
Проверочные контейнеры работают без внешних/опубликованных портов: Caddy и
клиент соединяются через loopback внутри одной network namespace.
Gosu получает только SETUID/SETGID, Caddy работает как 65534:65534 без capabilities.
Одноразовые контейнеры и созданный том удаляются; подготовленные файлы и
бинарники сохраняются локально для проверки.

Оркестрация и проверки артефактов — Python. Небольшой
`deploy/go-rebuild/tls_probe.go` использует stdlib уже выбранного компилятора,
чтобы проверить настоящий HTTP/2 без установки дополнительных сетевых пакетов.
Тестовая CA живёт только в tmpfs, доверие Windows/Linux не изменяется.
`default_sni localhost` используется только в тестовом Caddyfile: клиент
по IP получает localhost certificate, затем обязан вернуть конкретный
`x509.HostnameError`. Без этого Caddy отвергал handshake до проверки SAN.

## Граница результата

Совпадение двух binaries с этой версией готового Go toolchain подтверждено
фактической пересборкой. Это не bootstrap компилятора из его source tar,
не воспроизводимость всех слоёв Docker и не завершение остальных native/source
проверок или внешней приёмки. Исторические source/Docker kits не менялись.

[Результат и квитанция](../task-results/PM-023-go-build-20261124.md).
Технические основания: [Go module cache](https://go.dev/ref/mod#module-cache),
[Go environment](https://go.dev/ref/mod#environment-variables),
[Caddy default_sni](https://caddyserver.com/docs/caddyfile/options#default-sni).
