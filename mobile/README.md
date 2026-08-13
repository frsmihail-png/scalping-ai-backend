# Scalping AI Android

Android-приложение для существующей панели Scalping AI DEMO.

## Что внутри

Приложение открывает защищённую веб-панель:

`https://scalping-ai-backend-ishr.onrender.com/panel`

Поэтому в Android доступны те же функции, что и в браузере:

- AUTO START
- STOP AUTO
- EMERGENCY STOP
- CLOSE ALL
- баланс DEMO
- текущий signal/confidence
- Entry / SL / TP
- открытые позиции и PnL

## Локальный запуск через Expo Go

Требуется Node.js 20.19+.

```bash
cd mobile
npm install
npx expo start
```

## Сборка APK через EAS

```bash
cd mobile
npm install
npm install -g eas-cli
eas login
eas build -p android --profile apk
```

Профиль `apk` уже настроен в `eas.json` через `android.buildType=apk`.

## Важно

Приложение сейчас работает только с DEMO backend. API-ключи Binance не хранятся в APK и остаются на Render.
