# Переносимый локальный комплект MarkeTOB

10 ноября 2026 · PM-024-R2 · Linux/amd64 · schema-20261109.
Скопируйте весь каталог комплекта на другой компьютер. Нужны Docker с Linux
containers, Compose 2.24.4+ (`!override`) и Python 3.14 для проверки. На Windows
команды Docker ниже выполняются через настроенный WSL Ubuntu. Сами images не
требуют Python, Node, Git или компилятора на компьютере получателя.

## Проверить комплект

Из каталога комплекта, до загрузки образов:

```text
python -I verify.py --verify . --sha256 <ожидаемый-SHA256-квитанции>
```

Ожидаемый хеш receipt.json берите из опубликованного отчёта проекта или другого
доверенного канала. SHA256SUMS рядом с файлами сам по себе не подтверждает
автора. Цифровая подпись не создаётся. Verifier работает без Docker/Git/сети,
проверяет состав и все файлы, image config IDs, хеши и порядок слоёв, совпадение
Docker/OCI metadata и отсутствие тегов. Содержимое слоёв не извлекается и не
исполняется. Поддержан конкретный проверенный single-image Docker-save формат;
неподдерживаемый формат требует отдельной проверки.

В каталоге должны оставаться только доставленные файлы. Результаты проверок,
конфигурацию и заметки сохраняйте отдельно.

## Загрузить и запустить на Windows / WSL Ubuntu

Откройте PowerShell в каталоге комплекта. Эти команды загружают образы по IDs,
без переназначения tags; Docker не загружает пользовательские volumes.
Обычное поведение save/load описано в [Docker save](https://docs.docker.com/reference/cli/docker/image/save/)
и [Docker load](https://docs.docker.com/reference/cli/docker/image/load/).

```powershell
wsl -d Ubuntu --exec docker image load --input api.tar
wsl -d Ubuntu --exec docker image load --input bot.tar
wsl -d Ubuntu --exec docker image load --input db.tar
wsl -d Ubuntu --exec docker image load --input proxy.tar
python prepare.py --output ../marketob-run
wsl -d Ubuntu --exec docker compose --env-file ../marketob-run/.env -f compose.yaml -f compose.local.yaml -f compose.images.yaml up --detach --no-build --pull never --wait --wait-timeout 120
```

На Linux используйте те же команды без префикса `wsl -d Ubuntu --exec`.
На Windows Python может вызываться `py -3.14` вместо `python`.
Готовый интерфейс: [My Space](http://127.0.0.1:18000/app/#/space). Создайте
локальный аккаунт через Create account. Google/Firebase не нужны. Изначально
БД пустая; свои боты и каналы подключаются через Studio и HTTP API.

prepare.py создаёт **новый** каталог с приватным .env и случайными паролем/именем
Docker project. Существующий каталог не перезаписывается. Чтобы выбрать другие
свободные порты, добавьте `--port 18001 --https-port 18444`. Затем всегда
используйте этот же .env: смена project name создаёт отдельную пустую БД.
Пароль не печатается. .env не включайте в пересылаемый комплект.

Compose закрепляет image IDs, отключает build/pull и публикует порты только на
loopback. Бот включён отдельным image; постоянный запуск бота требует его
индивидуального ключа и конфигурации. БД, рабочие ключи и CA исходного компьютера
не переносятся. Новый proxy создаёт новую локальную CA. HTTPS доступен через
`https://localhost:18443`; доверие к этой CA настраивается отдельно и не меняется
автоматически. Для первого знакомства используйте HTTP loopback выше.

Остановить сервисы, сохранив данные:

```powershell
wsl -d Ubuntu --exec docker compose --env-file ../marketob-run/.env -f compose.yaml -f compose.local.yaml -f compose.images.yaml stop
```

Повторный запуск — прежняя команда `up`. Не используйте `down --volumes` для
экземпляра, данные которого нужно сохранить. При ошибке занятости порта меняйте
порт в приватном .env и allowed origins согласованно; не пересоздавайте пароль
у существующей БД. Для новой независимой копии выбирайте новый output/порты.

## Что передаётся

`api.tar`, `bot.tar`, `db.tar`, `proxy.tar` — четыре отдельные tagless-выгрузки.
`receipt.json` связывает их immutable IDs, размеры и SHA-256 с исходным commit.
`sources.tar` — проверенный исходный комплект, `source-receipt.json` — его
опубликованная квитанция. `recipe.json` сохраняет исходную привязку и открытые
пункты. Compose-файлы, prepare.py, verify.py и README входят в проверяемый состав.

После проверки можно извлечь sources.tar в отдельный пустой каталог. Внутри
находятся проектный и tooling Git-снимки, notices, исходные материалы и GAPS.md.
project.tar содержит API/SDK/ботов и документацию API; tooling.tar — материалы
сборки исходного комплекта. Текущий Docker-kit tooling_commit указан отдельно
в receipt.json. Это разные документированные снимки, а не одна Git revision.

Source coverage остаётся **partial**: все прежние gaps сохранены. Комплект
предназначен для локального пилота; он не означает завершённую внешнюю приёмку,
полный автономный rebuild, Android/Windows native-приложение, ARM64-поддержку
или облачное развёртывание. Личная приёмка и отложенные проверки остаются открытыми.
