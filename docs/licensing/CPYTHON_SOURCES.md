# Исходники CPython установленной поставки

24 ноября 2026 · PM-023-CPY · schema-20261109.

Для API и бота собран официальный исходный архив **CPython 3.14.9**.
Его SHA-256 совпадает с `PYTHON_SHA256` обоих immutable images и опубликованной
[страницей Python 3.14.9](https://www.python.org/downloads/release/python-3149/).
Образы с новой версией Python в этой задаче не собирались и не устанавливались.

## Что передавать

Локальный каталог `.local/pm023/cpython-20261124/kit/`: **11 файлов,
24 883 429 байт**. Передавайте каталог целиком. Внутри — исходный tar.xz,
source plan, inventory, наблюдения API/бота, установленная лицензия, patchlevel.h,
pyconfig.h, Makefile, standalone verifier и README. Личные данные и bot keys
в комплект не входят. Это дополнение к историческим Docker/source kits.

Квитанция лежит рядом с каталогом: `.local/pm023/cpython-20261124/receipt.json`.
Её [публичная копия](../task-results/assets/PM-023/cpython-20261124/receipt.json)
содержит независимый SHA-256 **manifest.json**:

```text
dce9641bb63d430b0037b22697809986e5c61186294adb879e47dcb96668ecd4
```

## Проверка без сети

Нужен Python 3.11+; фактически проверены Windows 3.14.7 и Linux 3.14.9.
Используйте проверенную копию [утилиты](../../scripts/cpython_sources.py).
Из каталога комплекта:

```text
python -I verify.py --verify . --sha256 dce9641bb63d430b0037b22697809986e5c61186294adb879e47dcb96668ecd4
```

Утилита сверяет независимый manifest hash, точный состав и каждый файл,
привязку source plan к двум image IDs, версии и source hash, все 5 571 записи
исходного архива и побайтовое совпадение LICENSE/patchlevel с установленными.
Она не требует Git/Docker/сторонних библиотек, не запускает build scripts
и не извлекает файлы из исходного дерева. Заметки и результат команды сохраняйте
вне каталога: лишние файлы отклоняются проверкой.

## Повторение разработчиком

Из корня репозитория:

```text
python -m scripts.cpython_sources --check-plan
python -m scripts.cpython_sources --collect .local/cpython-source-kit --fetch
```

Вместо `--fetch` можно передать `--source` с уже полученным tar.xz. Output должен
быть новым каталогом под `.local`. Ошибка оставляет `INCOMPLETE.txt`.
Хеш нового manifest может меняться вместе с verifier/README; сохраняйте квитанцию
каждой сборки вне её каталога. Сам upstream tar передаётся без изменения байтов.

Для повторного снятия наблюдений с сохранённых образов, без пользовательских
volumes, сети и writable container filesystem:

```text
python -m scripts.cpython_sources --probe .local/cpython-image-observations --wsl Ubuntu
```

На Linux с непосредственным Docker опустите `--wsl Ubuntu`. Команда не скачивает
образы: нужны прежние immutable IDs из release recipe. Сохраняются только два
разрешённых значения environment и заданные version/build/file сведения.

## Границы доказательства

Совпали LICENSE и Include/patchlevel.h, API/бот имеют одинаковые interpreter/
libpython hashes и build observations. Это проверяемая связь исходного архива
с записанными сведениями образов; полная воспроизводимая сборка не выполнена.
Sigstore-подпись не проверялась. Компилятор, полный набор build dependencies,
Go inputs, native linking и общая приёмка остаются открытыми.

[Отчёт](../task-results/PM-023-cpython-20261124.md) ·
[Исходный план](../../third_party/cpython-schema-20261109/source-plan.json).
