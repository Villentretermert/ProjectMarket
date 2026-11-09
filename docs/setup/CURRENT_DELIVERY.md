# Текущая локальная поставка · schema-20261109

9 ноября 2026. Рабочее приложение: [My Space](http://127.0.0.1:19000/app/#/space).
Состояние полного проекта — 19/24; Android, облако и полный L2 отложены.
Ниже отдельно описаны исходный комплект и проверка установленного Linux-набора.

## Артефакты

- [Source recipe](../../third_party/delivery-schema-20261109/recipe.json) связывает
  четыре image IDs с исходным commit `896449bde9cdec4cea9f7ce29eba6910285da30e`.
- [Квитанция архива](../task-results/assets/PM-023/handover-schema-20261109/receipt.json).
  Локальный каталог: `.local/pm023/handover-schema-20261109-02/`.
  Передайте tar, verifier, receipt, SHA256SUMS и README вместе.
- [Проверка исходного комплекта](../licensing/SOURCE_HANDOVER_SCHEMA.md) работает
  без Git/Docker/сети. Комплект не содержит исполняемые Docker images.
- [Пилотные боты](PILOT_BOTS.md), [HTTP API](../api/PROTOCOL.md) и
  [инструкция владельцу](PILOT_HANDOFF.md).

| Роль | Immutable image ID |
| --- | --- |
| API / мигратор / maintenance | `sha256:97570a3fc6ce9a11509b589c33c55ab8e01e75045c582046d1b616d4adbd53b8` |
| Python bots | `sha256:a93b10c759b741ae247e8b6a2571ce7feeba32bbc1756e7fc8c1c5d9936db582` |
| PostgreSQL | `sha256:07aa878e696f9eca7e46515ba052c6f80f1372d09686cfb7b71ba49054b5a52f` |
| HTTPS proxy | `sha256:031c3f1f15156d1a0054dbe3328220c81ca0090b9dab5384fd0210d88672164b` |

Теги могут быть переназначены, поэтому проверка ниже запускает именно IDs.
На этом компьютере они уже установлены. Для другого компьютера images нужно
доставить отдельно через Docker save/load и сверить IDs с recipe. Пересборка из
исходников может дать другие IDs и требует собственного inventory/binding;
не подменяйте хеши recipe ради прохождения проверки.

## Повторить чистую проверку на этом компьютере

Нужны полный Git clone с историей, настроенная `.venv-dev`, WSL Ubuntu с Docker
Compose (поддержка `!override`), Node и `apps/client/node_modules` из lockfile.
На Windows можно использовать установленный Edge. Проверка создаёт отдельные
случайные loopback-порты, Docker project/volumes и одноразовые аккаунты.

Из корня репозитория в PowerShell:

```powershell
.venv-dev/Scripts/python.exe -m scripts.delivery_bundle --recipe third_party/delivery-schema-20261109/recipe.json --check-recipe
$env:MARKETOB_BROWSER_CHANNEL='msedge'
.venv-dev/Scripts/python.exe -m scripts.smoke_release --wsl Ubuntu --output .local/pm024/my-delivery-check
```

Выберите новый output-каталог при повторе: существующий результат не
перезаписывается. Скрипт требует наличие всех четырёх images, ничего не строит
и не заменяет в рабочем `marketob-pm021`. Создаются новая БД и CA только для
проверочного клиента; доверие ОС не меняется. Рабочий пилот остаётся запущенным.

Проверяется: миграция пустой БД, worker, HTTPS/CA/Secure cookie, точные IDs
запущенных контейнеров, HTTP-публикация каталога и синтетической RSS, закрытый
доступ, Favorites, визуальный выбор блоков My Space, Card/автосохранение/Undo и
одна заявка с реальным ответом Docker-бота. RSS читается из fixture без внешней
сети; это не повторная проверка доступности Meduza.

После успешного завершения `release.json` содержит безопасные метаданные,
`result.json` — браузерные результаты; `my-space.png`, `confirmed.png` и
`marketob-my-space.webm` показывают синтетический сценарий. Одноразовые
контейнеры/volumes удаляются в `finally`, в том числе при ошибке. Приватные
конфигурации теста остаются в игнорируемом `.local/docker_load_*`; их не публикуют.

Для личного знакомства используйте рабочий My Space и
[короткий пользовательский сценарий](PILOT_HANDOFF.md#первый-опыт-товары-и-новости).
Автоматическая проверка не заменяет вашу личную приёмку, Android-телефон,
магазинную публикацию, полный L2 или незакрытые source/build gaps.
