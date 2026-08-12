# Scalping AI Backend v0.2

FastAPI backend for the Expo mobile app. It uses Binance public Spot market data only; no API keys and no real orders.

## Windows quick start

```bat
cd backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://127.0.0.1:8000/health` on the PC. It should return `{\"ok\":true}`.

For an Android phone on the same Wi-Fi, set `EXPO_PUBLIC_API_URL` in `mobile/.env` to the PC's LAN IP, for example:

```env
EXPO_PUBLIC_API_URL=http://192.168.1.50:8000
```

Do NOT use `127.0.0.1` in an installed Android APK unless the backend is running on the phone itself.

## Endpoints

- `GET /health`
- `POST /analyze`

Example body:

```json
{"symbol":"BTCUSDT","interval":"1m"}
```

## Current strategy

Multi-timeframe 1m/3m/5m/15m scoring using EMA 9/21/50/200, RSI, MACD, ADX, ATR, Bollinger Bands, VWAP, volume ratio, support/resistance and an anti-chasing filter.

This is PAPER MODE. It does not place real orders.
