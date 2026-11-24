# Исходные материалы Go · schema-20261109

24 ноября 2026 · PM-023-GO. Дополнение к историческим source/Docker kits.

Для двух установленных программ собраны все входы из сохранённых `go.sum`:
221 module ZIP и 370 go.mod (591 запись), а также исходники Go 1.26.10 и gosu
1.19. Одинаковые байты хранятся один раз. 162 зависимости присутствуют в
метаданных бинарников; остальные записи не объявляются runtime dependencies.

Сохранены builder go.mod/go.sum, build metadata, Caddy main и исходные Go-файлы
gosu. Бинарники Caddy/gosu побайтово совпали с указанными в inventory builders.
В них повторно выполнен `go mod verify` без сети. Извлечённые VERSION/LICENSE/
PATENTS совпали с официальным Go source tar, Go notices — с runtime inventory.

## Получателю

Передайте каталог `.local/pm023/go-20261124/kit-03/` целиком и
[квитанцию](../task-results/assets/PM-023/go-20261124/receipt.json) отдельно.
584 файла, 246 872 827 байт. SHA-256 `manifest.json`:

```text
1219282099550462950ae09cbf9a78a095d601be746f3a73607d03d5e8caf43e
```

Из каталога комплекта, Python 3.11+:

```sh
python -I verify.py --verify . --sha256 1219282099550462950ae09cbf9a78a095d601be746f3a73607d03d5e8caf43e
```

Проверка не использует сеть, Git, Go или Docker. Она проверяет точный список
файлов, размеры/SHA-256, весь набор go.sum, Go h1 содержимого ZIP/go.mod,
привязку модулей к binary inventory и исходные файлы. Архивы не распаковываются,
исходники и ссылки внутри архивов не исполняются. Заметки и вывод проверок
сохраняйте снаружи каталога. `source-plan.json` сопоставляет хеш-имена архивов
с модулем, версией, URL и ролями. Сначала проверьте доверие к полученным
verifier/квитанции: их самопроверка не заменяет независимую подпись.

## Разработчику

Из репозитория; каждый output должен быть новым:

```powershell
.venv-dev/Scripts/python.exe -m scripts.go_sources --check-plan
.venv-dev/Scripts/python.exe -m scripts.go_sources --probe .local/go-probe-new --wsl Ubuntu
.venv-dev/Scripts/python.exe -m scripts.go_sources --collect .local/go-kit-new --fetch
```

Probe требует сохранённые runtime/builder images, перечисленные в inventory;
запускает одноразовые контейнеры без сети/volumes с read-only filesystem.
Он записывает только перечисленные общедоступные сведения и сверяет их
с сохранённым evidence. Сбор с `--fetch` получает точные upstream bytes;
`--inputs <каталог-комплекта>` позволяет повторить сбор без сети.
Собственный verifier нормализуется в LF, исходные наблюдения сохраняются побайтово.
CI повторяет сетевой сбор и требует опубликованный manifest hash.

## Границы

Это набор исходных входов, а не готовое средство автономной пересборки.
Нет `.info` metadata для готового GOPROXY tree, bootstrap toolchain binaries
или доказательства полной воспроизводимости бинарников. Исторический Dockerfile
proxy содержит `go get`; для воспроизводимой последующей сборки нужно использовать
сохранённые go.mod/go.sum, а не заново разрешать версии по этому Dockerfile.
Полный offline rebuild компилятора/образов, native graph, остальные source/
attribution gaps и внешняя приёмка остаются открытыми. Новая проверка sumdb
подписи не заявлена. Работающие images и исторические kits не обновлены.

Источники: [официальный каталог Go](https://go.dev/dl/?mode=json&include=all),
[описание go.sum](https://go.dev/ref/mod#go-sum-files),
[алгоритм Go h1](https://github.com/golang/mod/blob/master/sumdb/dirhash/hash.go).
Сохранённые SHA-256/версии являются основанием этого комплекта, а текущая ветка
документации описывает алгоритм. [Результат](../task-results/PM-023-go-20261124.md).
