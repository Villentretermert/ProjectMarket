# Android: продолжение проверки после паузы

21 октября 2026: владелец выбрал «Пока отложить Android-сборку» и «Подключу позже». SDK-лицензии **не приняты**, пакеты Platform/Build-Tools/Platform-Tools не установлены, APK не собран. Эти шаги выполняются только после возобновления Android-работы.

## Что уже подготовлено

- `spikes/client-web-native/android`: Android-проект, native news widget и мост JavaScript/Java. Исходники ещё не прошли компиляцию/устройство.
- `.local/toolchains/jdk21`: официальный Temurin `jdk-21.0.12.1+1`, архив проверен по SHA256 поставщика `f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e`.
- `.local/toolchains/android-sdk/cmdline-tools/12.0`: официальные Android command-line tools. Текст непринятой лицензии сохранён в `.local/android-sdk-license-review.txt`, вне Git.
- Нужны `platform-tools`, `platforms;android-36`, `build-tools;36.0.0`. Наличие command-line tools само по себе не означает готовый SDK.

## Возобновление

1. Прочитать [условия Android SDK](https://developer.android.com/studio/terms); владелец принимает их через `sdkmanager` либо явно разрешает принятие. Предыдущий ответ — отложить, поэтому автоматически не принимать.
2. Установить перечисленные пакеты, закрепить `JAVA_HOME` на JDK 21 и `ANDROID_HOME` на локальном SDK только для текущей команды. Проверить Gradle/JDK и конкретный `applicationId`.
3. `npm ci`, `npm run build`, `npx cap sync android` из `spikes/client-web-native`; затем Gradle `assembleDebug` из `android`. В текущем Windows-пути есть кириллица/пробелы: если AGP отклонит путь, выполнять сборку из временной ASCII-копии; не отключать path-check без проверки результата.
4. На телефоне включить Developer options → USB debugging, подключить USB и подтвердить ключ именно этого компьютера. `adb devices` должен показывать `device`, а не `unauthorized`. Серийный номер не публиковать в Git/чате.
5. Установить debug APK. В приложении открыть Daily Brief → Update demo widget → Add home widget. Проверить настоящий launcher, заголовки, переход в новости после закрытия приложения и Clear widget cache. Записать модель/Android version без идентификаторов устройства и фактический результат.
6. Для будущего API на компьютере использовать `adb reverse tcp:8000 tcp:8000`; `localhost` телефона без reverse не является компьютером. Этот spike имеет bundled public data, поэтому backend ему не нужен.

PM-019 нельзя закрывать без сборки/устройства; PM-020 — без настоящего виджета и private cache/TTL/logout проверок. На PM-002 этого не заявляем.

Официальные инструкции: [USB device](https://developer.android.com/studio/run/device), [sdkmanager](https://developer.android.com/tools/sdkmanager), [Capacitor environment](https://capacitorjs.com/docs/getting-started/environment-setup).
