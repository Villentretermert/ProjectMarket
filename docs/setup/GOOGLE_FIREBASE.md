# Google / Firebase для локального MarkeTOB

> Отложено по ответу владельца 2026-10-21: текущий пилот без облака. Сейчас создавать проект не требуется. Эта инструкция сохранена для следующего сетевого этапа.

PM-002 · 21 октября 2026. Владелец создаёт проект; текущий прототип использует только demo данные. Сначала достаточно выполнить шаг 1 и сообщить **project ID** (он не секрет). Не присылать client secret, service-account JSON или пароли в чат.

## 1. Создать проект

Откройте [Firebase Console](https://console.firebase.google.com/) и создайте проект с отображаемым именем MarkeTOB Pilot. Сохраните его project ID. Analytics и дополнительные AI-функции для нашего spike не нужны; их можно не включать. Если появляется принятие условий, прочитайте и подтвердите их самостоятельно. Создание Firebase проекта также создаёт связанный Google Cloud проект. [Официальная инструкция](https://firebase.google.com/docs/android/setup).

## 2. Настроить Google как способ входа

В Authentication включите Google provider и задайте support email. Это настройка провайдера, а не создание пользовательских паролей в MarkeTOB. Добавьте свои тестовые аккаунты, если консоль запрашивает список пользователей в testing mode. [Инструкция Google sign-in](https://firebase.google.com/docs/auth/android/google-signin).

Архитектурная граница: APK/Web не хранят client secret. Backend проверяет issuer/audience/expiry и выдаёт свою сессию; токен бота не используется для входа человека. Окончательный клиентский flow выберем после сравнения стека, поэтому создавать несколько конкурирующих OAuth клиентов сейчас не требуется.

## 3. Android — после фиксации сборки

Планируемый debug package: `com.villentretermert.marketob.pilot`. Перед регистрацией сверить его с фактическим applicationId собранного прототипа. Зарегистрировать Android app в проекте. SHA-1/SHA-256 берутся из **реального** debug signing certificate; я подготовлю значения после готовой сборки. Не копировать случайный fingerprint из примеров.

После добавления fingerprint и Google provider скачать обновлённый `google-services.json` и сохранить локально в `.local/secrets/google-services.json`. Каталог `.local/` исключён из Git. Публичные идентификаторы Firebase не равны приватному серверному ключу; это всё равно конфигурация конкретного окружения. [Настройка Android](https://firebase.google.com/docs/android/setup), [Google authentication](https://firebase.google.com/docs/auth/android/google-signin).

## 4. Web / backend — когда клиентский flow определён

Если выбран серверный OAuth, создать **Web application** OAuth client в связанном Cloud-проекте. Предварительный локальный redirect: `http://localhost:8000/v1/auth/google/callback`; этот адрес должен точно совпасть с реализацией PM-004/006 перед проверкой. До реализации callback вводить секрет в прототип не нужно. Для Google Identity Services origins задаются отдельно от redirect URI; не подменять одно другим. [Web server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server).

Server client secret хранить только в локальном исключённом конфиге backend. Для Android потребуется отдельный public-client/native flow или защищённая передача одноразового login result; secret из Web application нельзя переносить в APK.

## 5. Push — после готового клиента

В PM-018/019 связать Android app с FCM и проверить notification permission/token на устройстве. Для Web Push дополнительно нужны service worker и VAPID public key. Backend отправляет сообщения от доверенного серверного окружения; приватные credentials не попадают клиенту. Сейчас сервисный JSON не требуется — не создавайте долгоживущий ключ заранее. [FCM HTTP v1](https://firebase.google.com/docs/cloud-messaging/send/v1-api).

## Что нужно для продолжения

- После шага 1: project ID и подтверждение включённого Google provider.
- После Android-сборки: Android app с нашим package и фактическим SHA, локальный путь к конфигурации.
- Для live-проверки: владелец самостоятельно проходит Google-вход и consent в браузере/на телефоне. UI заглушка не считается такой проверкой.

Ни Firebase, ни Google OAuth, ни FCM ещё не подключены к прототипу. Политики/названия консоли могут меняться; приведённые официальные страницы проверены при подготовке инструкции.
