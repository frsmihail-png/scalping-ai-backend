# Scalping AI Backend v0.3 — DEMO Futures

FastAPI backend for market analysis plus guarded Binance USD-M Futures DEMO execution. LIVE trading is intentionally blocked in v0.3.

## Safety profile

- DEMO only
- leverage fixed to 3x
- default risk budget: 0.5% of available USDT per trade
- maximum margin allocation: 25% of available balance
- daily loss guard: 2%
- minimum signal confidence: 78%
- duplicate position protection
- explicit `confirm=true` required for every open/close request
- symbol allowlist

A 1% profit per trade is NOT guaranteed. The engine sizes risk; it does not promise returns.

## Render environment variables

Add these in Render -> Service -> Environment. Never commit API secrets to GitHub.

```env
TRADING_MODE=DEMO
ENABLE_DEMO_TRADING=false
BINANCE_DEMO_API_KEY=YOUR_DEMO_KEY
BINANCE_DEMO_API_SECRET=YOUR_DEMO_SECRET
BINANCE_DEMO_FUTURES_URL=https://demo-fapi.binance.com
BOT_LEVERAGE=3
BOT_RISK_PER_TRADE=0.005
BOT_MAX_DAILY_LOSS=0.02
BOT_MAX_CONSECUTIVE_LOSSES=3
BOT_MIN_CONFIDENCE=0.78
BOT_MAX_MARGIN_FRACTION=0.25
BOT_ALLOWED_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT
```

Keep `ENABLE_DEMO_TRADING=false` for the first deployment. Check `/trade/demo/status`; only then switch it to `true`.

## Endpoints

- `GET /health`
- `POST /analyze`
- `GET /trade/demo/status?symbol=BTCUSDT`
- `POST /trade/demo/open?symbol=BTCUSDT&interval=1m&confirm=true`
- `POST /trade/demo/close?symbol=BTCUSDT&confirm=true`

## Important v0.3 limitation

The first DEMO execution milestone validates authenticated connectivity, leverage, position sizing, duplicate-entry protection and market entry/close. Automatic server-side protective SL/TP is deliberately not enabled yet; validate DEMO order behavior first. Do not use this branch for real funds.

## Local start

```bat
cd backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
