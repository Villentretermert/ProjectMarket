# Исходники установленных Python-пакетов

24 ноября 2026 · дополнение к schema-20261109, PM-023-PY.

Собраны все 30 уникальных сторонних PyPI-пакетов из inventory API/бота:
29 в API, 6 в боте, 5 общих. Шесть native sdists уже были в прежнем комплекте;
24 добавлены впервые. Собственный код остаётся в Git-снимке исходной поставки.
Названия, версии, URL, размеры и SHA-256 сверены с `uv.lock` commit
`896449bde9cdec4cea9f7ce29eba6910285da30e`; корневой `PKG-INFO` каждого архива
сверен с установленным пакетом. Поиск новой версии пакетов не выполнялся.

## Комплект и проверка получателем

Локальный каталог: `.local/pm023/python-sources-20261124-02/`.
Основной файл: `python-runtime-sources.tar`, **14 735 360 байт**.
Передайте tar, `verify.py`, `receipt.json`, `SHA256SUMS` и эту инструкцию.
Нужен Python 3.11+; фактически проверены Windows 3.14.7 и Linux 3.14.9.

SHA-256 архива из опубликованной квитанции:

```text
102d3b95e5800c49bae69f3ea9f81411e58948af1cd66d59976a0cbf1ee9cd5f
```

Сначала сравните хеш tar с этой независимой копией (а не только с файлом,
полученным вместе с архивом). PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\python-runtime-sources.tar
```

После совпадения можно извлечь только проверяющую утилиту из уже проверенного
tar, затем выполнить проверку состава. Linux использует `sha256sum` для первого
шага; команды ниже одинаковы на обеих ОС:

```text
tar -xf python-runtime-sources.tar verify.py
python -I verify.py --verify python-runtime-sources.tar --sha256 102d3b95e5800c49bae69f3ea9f81411e58948af1cd66d59976a0cbf1ee9cd5f
```

Проверка работает без Git, сети, Docker и сторонних Python-библиотек. Она
сверяет состав, inventory/lock, каждый sdist и PKG-INFO, не распаковывает
исходные деревья и не выполняет `setup.py`/build backend.
Криптографическая подпись издателя этим SHA-256 не заявляется.

## Повторный сбор разработчиком

Из корня репозитория с Python 3.11+ и Git:

```text
python -m scripts.python_sources --check-plan
python -m scripts.python_sources --collect .local/python-runtime-sources --fetch
```

Без `--fetch` сбор использует только уже проверяемый локальный cache.
Каталог назначения должен быть новым. Ошибка оставляет `INCOMPLETE.txt`;
такой результат передавать нельзя. Хеш повторной сборки зависит также от
точных байтов упакованного verifier; сохраните её собственную квитанцию.
В CI проверка mapping выполняется на Windows/Linux, повторное получение
всех sdists — на Linux.

## Границы результата

Это отдельное дополнение: старые receipts, source tar и Docker kit не изменены.
Оно закрывает получение верхнеуровневых runtime sdists, но не весь пункт
`remaining-source-inputs`. CPython 3.14.9, Go/toolchains, транзитивные build
dependencies, точные native feature/link maps, полная пересборка и прежние
проверки релиза открыты. Версия sdist не доказывает происхождение байтов wheel.
Полная PM-023 и счётчик 19/24 сохраняются.

[Манифест](../../third_party/python-sources-schema-20261109/manifest.json) ·
[Результат](../task-results/PM-023-python-sources-20261124.md).
