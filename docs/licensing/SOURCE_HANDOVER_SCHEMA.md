# Исходный комплект schema-20261109

9 ноября 2026. Комплект относится к текущим Linux-образам MarkeTOB:
API/maintenance, bot, DB и proxy. Это собранные исходные материалы с охватом
`partial`, не Docker images, APK или автономная полная пересборка.

Получателю передаются `marketob-sources-schema-20261109.tar`, `verify_bundle.py`,
`SHA256SUMS`, `receipt.json` и эта инструкция (`README.md`). Исторический комплект
68958f1 сохранён отдельно; для новых API/bot используйте новый receipt.

## Проверка перед распаковкой

На Python 3.14, без Git, Docker и сети:

```text
python -I verify_bundle.py --verify marketob-sources-schema-20261109.tar --sha256 <ожидаемый-SHA256>
```

Ожидаемый SHA-256 берётся из опубликованной квитанции проекта или доверенного
канала. Соседний SHA256SUMS обнаруживает повреждение, но не подтверждает автора;
цифровой подписи нет. Проверяются весь tar, манифест, состав, типы, размеры и
хеши файлов. Ничего не извлекается и не исполняется. `integrity=verified`
подтверждает целостность; `coverage_state=partial` сохраняет незавершённые пункты.

## Состав и связь с образами

| Вложенный файл | Назначение |
| --- | --- |
| manifest.json | Две Git revisions, четыре immutable image IDs, состав и SHA-256 |
| sources/project.tar | Точный исходный commit `896449bde9cdec4cea9f7ce29eba6910285da30e` |
| sources/tooling.tar | Коммит инструментов сборки, новые inventory/binding/recipe и прежние source evidence |
| sources/debian.tar | 95 исходных package/version, 304 pool-файла, 11 metadata |
| sources/alpine.tar.gz | 187 recipe/source inputs для 20 origins |
| sources/python-rust.tar.gz | 6 Python sdists, 450 crates, 26 upstream-файлов |
| sources/modified-psycopg.tar.gz | Дерево из выполненной проверки замены драйвера |
| GAPS.md, LICENSE, NOTICE | Открытые пункты, лицензия и уведомление проекта |

Четыре внешних source-архива сохранены побайтно. Новый binding фиксирует
совпадение установленного component/notice inventory, native wheels и собственных
исходников с ранее собранными материалами. Он находится в tooling:
`third_party/schema-20261109/binding.json`. Семь групп open_items не закрываются
переносом в новый комплект. 546 различных расширенных notice texts находятся
в исторических native/crate архивах; свежий базовый inventory содержит 259.

После успешной проверки распакуйте основной tar в новый пустой каталог, а
project.tar и tooling.tar — в два отдельных пустых каталога. Внутренние файлы Git
сверены с blob-объектами при сборке; архивы не содержат историю Git, локальные
credentials, .env, backups или данные работающего приложения.

Самостоятельная проверка tar не требует checkout. Повторная проверка **release
binding** сравнивает исходные файлы с историческим Git commit и требует полного
клона репозитория; один распакованный tooling.tar историю не содержит:

```text
python -m scripts.release_binding --verify third_party/schema-20261109/binding.json
python -m scripts.delivery_bundle --recipe third_party/delivery-schema-20261109/recipe.json --check-recipe
```

Полный исходный комплект не выдаётся за готовый установщик. Запуск, личная
приёмка, отдельная доставка Docker images, недостающие build inputs и остальные
пункты GAPS.md сохраняют собственные критерии проверки.
