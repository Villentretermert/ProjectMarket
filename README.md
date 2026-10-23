# MarkeTOB

Платформа витрин для ботов: B2B владелец публикует страницу с данными своего сервиса, B2C пользователь сохраняет страницы и собирает собственный интерфейс из разрешённых блоков.

**Состояние на23 октября2026:** завершены PM-001–018 и PM-021, **19/24** задач пилота. Работают локальные аккаунты, роли, боты, каналы, заявки, Studio, избранное, My Space и Share/Import. Открытый Web автоматически обновляет источники, сохраняет правки оформления и показывает выбранные Events. [CI PM-021](https://github.com/Villentretermert/ProjectMarket/actions/runs/39948316689):153 tests,47 Chromium scenarios, все4 jobs PASS. Локальные Docker/restore/HTTPS и Edge preview проверены. Локальный L1:1500/1500 rendered, p95 2.467s, p99 2.625s. После G04:3/4. Android/виджет и Google/Firebase/облако отложены. Интерфейс — английский.

## Запустить локальный backend

[Локальная поставка](docs/setup/LOCAL_DELIVERY.md) · [Backup/restore](docs/setup/BACKUP_RESTORE.md) · [Разработка](docs/setup/LOCAL_DEVELOPMENT.md). На текущем компьютере доступны Python и Docker внутри Ubuntu WSL; PM-021 принята: HTTPS, backup/restore, restart; 153 теста и 47 браузерных сценариев PASS.

## Рабочий Web

[Открыть работающий локальный пилот](http://127.0.0.1:19000/app/) (проект marketob-pm021). Создайте свой аккаунт через Create account. [Инструкция Web и проверка браузером](docs/setup/WEB.md).

## Начать работу

1. Прочитать [регламент](docs/WORKING_AGREEMENT.md).
2. Прочитать [ответы и открытые вопросы](docs/DISCOVERY_QUESTIONS.md); Q01–Q17 уже учтены.
3. Выбрать задачу в [плане](docs/ROADMAP.md): например, «Сделай PM-017» после G04.
4. Проверить [текущее состояние](docs/STATUS.md) и [открытые решения](docs/DECISIONS.md).

## Проектные материалы

- [Продукт и границы пилота](docs/PRODUCT_BRIEF.md)
- [Архитектура и сущности](docs/ARCHITECTURE.md)
- [Интерактивный дизайн и сценарии](docs/DESIGN.md)
- [Контракт ботов API 1.0](docs/api/PROTOCOL.md)
- [План: 24 задачи пилота и 4 задачи развития](docs/ROADMAP.md)
- [Реестр GitHub Issues](docs/GITHUB_ISSUES.md)
- [Контрольные точки и вопросы](docs/CHECKPOINTS.md)
- [Журнал изменений](CHANGELOG.md)

Документы — исходный план, а не обещание уже работающих возможностей. При изменении требований сохраняются стабильные идентификаторы задач и явно описывается пересмотр объёма. Существующие исследования владельца не заменяют текущий запрос.

## Локальный Web-прототип

[Запуск HTML/JS spike](spikes/client-web-native/README.md) · [Python/Flet comparison](spikes/client-flet/README.md) · [Результаты и снимки](docs/task-results/PM-002.md). Google/Firebase сейчас не нужны.

## Текущий интерактивный дизайн

[Запуск прототипа PM-003](design/prototype/README.md) · [Доказательства UI](docs/task-results/PM-003.md) · [Контракт и проверки PM-004](docs/task-results/PM-004.md). G01 завершена; G02 подготовлена и показана после PM-008.

[G01: презентация, системная схема и вопросы](docs/reviews/G01/README.md).

[G02: презентация и следующий этап](docs/reviews/G02/README.md).

[Запуск пилотных ботов](docs/setup/PILOT_BOTS.md) · [Python SDK](packages/bot-sdk/README.md).

[G03: результаты PM-009–012, презентация и вопросы](docs/reviews/G03/README.md).

[G04: Web, Studio, избранное и My Space](docs/reviews/G04/README.md).

[PM-017: обмен шаблонами](docs/task-results/PM-017.md) · [PM-018: live updates и Events](docs/task-results/PM-018.md)
· [L1: методика и измерения](docs/task-results/PM-018-LOAD.md).
