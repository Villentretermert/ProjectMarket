# Текущее состояние

**Дата:** 24 октября 2026. **Завершено:** 19/24 задач пилота, 0/4 развития.
**Текущий gate:** полный L2 PM-022 отложен владельцем до свободного компьютера
(D43). Нагрузочный стенд остановлен. Не запускать новый L2 без продолжения владельца.
**G02:** закрыта, все 12 ответов приняты. **После G02:** 4/4, PM-009–012 завершены.
**G03:** закрыта, все 13 ответов сохранены. Разрешён весь блок PM-013–016. После G03: 4/4; PM-013–016 done. G04 закрыта по указанию «Продолжай» 23 октября; допущения записаны отдельно. PM-017 done ([CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39924166312)), PM-018 done ([CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39929710247)). После G04: 3/4. Текущий результат:153 tests / 47 browser scenarios PASS; L1 1500/1500 rendered, p95 2.467s/p99 2.625s. PM-019/020 остаются отложены владельцем; G05 ещё не требуется.

**Последний результат D46:** реализованы личный JSON export, передача workspace
Owner → Admin и удаление с паролем + DELETE. [Отчёт](task-results/PM-023-account-privacy.md).
187 локальных tests PASS +4 Docker-only skips; contract25 и targeted7 PASS,
54 Edge-сценария PASS. CI ожидается. P1–P3 отвечены.
Исправление очереди отдельно принято по [CI40077334919](https://github.com/Villentretermert/ProjectMarket/actions/runs/40077334919):185 tests/49 Chromium, все4jobs PASS.
Ниже сохраняется хронология предыдущих этапов; её ожидания superseded D45/D46.

- Работают локальные аккаунты, сессии, B2B и права доступа; регистрация ботов и индивидуальные ключи; приём данных и хранение истории/квитанций по 30 дней.
- Готовы версии оформления, публикация и откат, snapshots с проверкой прав и ETag; Request purchase, GET/ACK/result, unknown и сверка результатов.
- Python SDK, независимые каталог/RSS-боты, инструкция запуска и Docker profile проверены.
- [CI PM-012](https://github.com/Villentretermert/ProjectMarket/actions/runs/39835253441): все 4 jobs PASS, 117 тестов, реальные сбои API/БД/worker/ботов и восстановление.
- Локальный baseline: 100 ботов, 10 читающих сессий, 3 000/3 000 сообщений за 180,139 с; p95 приёма 295,02 мс, чтения 253,76 мс. После restart сохранены все 3 000 receipt/outbox. Это API baseline, не полный L2/UI SLO.
- PM-013: рабочий Web /app/, local login, каналы, новости/товары/графики, заявки и восстановление после потери ответа. [CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39846617703) 118 tests + 14 Chromium сценариев PASS, Edge PASS. Studio, избранное и My Space также завершены; материалы G04 ниже.
- PM-014 Studio принята: [CI 39853394634](https://github.com/Villentretermert/ProjectMarket/actions/runs/39853394634), 125 tests и 24 Chromium scenarios PASS; локальный Edge PASS. PM-015 принята: [CI 39854053654](https://github.com/Villentretermert/ProjectMarket/actions/runs/39854053654), 130 tests и 29 Chromium scenarios PASS; Edge PASS. PM-016 принята: [CI 39858054474](https://github.com/Villentretermert/ProjectMarket/actions/runs/39858054474), 137 tests и 36 Chromium scenarios PASS; Edge PASS. My Space сохраняет layout отдельно от данных источников.
- Android SDK/сборка/USB и Google/Firebase/облако отложены владельцем. Docker28.1.1/Compose2.35.1 обнаружены в Ubuntu WSL; локальная поставка PM-021 проверена. Переносимая PostgreSQL работает на loopback:55432.
- Доставка outbox в открытый Web, Events/preferences и resync готовы. [Отчёт PM-018](task-results/PM-018.md). Backup/restore PM-021 проверены; полный L2/burst/monitoring — PM-022, приватность/cleanup и релизная проверка — PM-023.

[G04](reviews/G04/README.md) · [G03](reviews/G03/README.md) · [Отчёт PM-012](task-results/PM-012.md) · [Боты](setup/PILOT_BOTS.md) · [Стенд](setup/BACKEND_LAB.md) · [План](ROADMAP.md).

PM-021 done: локальная Docker-поставка в Ubuntu WSL, HTTPS, backup/restore и restart проверены. [CI](https://github.com/Villentretermert/ProjectMarket/actions/runs/39948316689): все4 jobs PASS. [Стенд](http://127.0.0.1:19000/app/) оставлен работающим. Следующая локальная задача PM-022, затем обязательная G05 после20 завершений. Android отложен.

PM-022 in_progress: отдельный локальный стенд, L2/burst и эксплуатационные ограничения; счётчик остаётся19/24 до приёмки.

24 октября: короткий Docker-прогон runtime2008583 с2 API-процессами прошёл все SLO,
2 000/2 000 rendered,live p95=2.084с;burst3 000/3 000,5 100 точных ID после restart.
CI40034156701:162 Python-теста/47 browser scenarios,все4jobs PASS. Полный1800с+burst
прерван после13мин по отсрочке владельца. Диагностика и предыдущие неудачные
повторы сохранены в [отчёте PM-022](task-results/PM-022.md). Облегчённый health probe
worker проверен отдельно; [CI d4bd845](https://github.com/Villentretermert/ProjectMarket/actions/runs/40037429124)
успешен во всех4jobs:81unit+86integration=167 Python-тестов и47 browser scenarios.
Новые образы d4bd845 подготовлены. Задача и G05 не приняты, рабочий
пилот пока на6b3ffb5.

24 октября, D44: по команде «Делай следующие задачи» начата независимая
Web/API-часть PM-023: доступ, экспорт и очистка данных. Полная приёмка остаётся
открытой; Android, облако и полный L2 отложены. Счётчик 19/24, G05 ещё не требуется.

PM-023: [частичный результат](task-results/PM-023.md), 29 targeted tests и
48 Edge browser scenarios PASS. Исправлены no-op role notifications, очистка
metadata удалённых сущностей и открытый purchase dialog при отзыве. Статический
scan: один Low finding переполнения общей очереди; общий revoke-path ещё требует
исправления. Два широких патча отклонены автоматической проверкой, не применены;
[предложение](proposals/PM-023-queue-safety.md) ожидает явного разрешения.
Три решения об export/delete ожидают ответов. Рабочий Docker всё ещё на6b3ffb5.
PM-024: [инструкция передачи](setup/PILOT_HANDOFF.md) подготовлена независимо,
полный RC и приёмка владельцем не выполнены. Счётчик остаётся19/24.

[CI 3d82143](https://github.com/Villentretermert/ProjectMarket/actions/runs/40045091707):
все4 jobs PASS, 81 unit +90 integration =171 Python tests и48 Chromium scenarios;
Docker/HTTPS/restore PASS. Рабочий локальный Docker этой проверкой не обновлялся.

**Последнее продолжение, D45:** ответ «Продолжай» после прямого запроса разрешил
исправление общей очереди. Оно применено; повторное разрешение не требуется.
[Отчёт](task-results/PM-023-queue-fix.md):76 targeted tests +3 усиленных controls,
49 Edge scenarios PASS; независимый review без конкретных обходов/регрессий.
CI40077334919 прошёл все4jobs. Предыдущие сообщения об ожидании разрешения исторические.
P1–P3 export/delete отвечены D46; Android/облако/L2 отложены;19/24, G05 ещё не наступила.
