import asyncio
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .binance_client import BinanceMarketDataError, fetch_klines
from .futures_client import BinanceFuturesError
from .indicators import parse_klines
from .models import AnalyzeRequest, AnalyzeResponse
from .risk import RiskRejected
from .strategy import analyze_frame, combine
from .trading import TradeRejected, close_demo_position, demo_status, demo_trade

load_dotenv()

app = FastAPI(title="Scalping AI API", version="0.3.0")

origins_raw = os.getenv("ALLOWED_ORIGINS", "*")
origins = [x.strip() for x in origins_raw.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"name": "Scalping AI API", "version": "0.3.0", "mode": os.getenv("TRADING_MODE", "DEMO").upper()}


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(body: AnalyzeRequest):
    intervals = ["1m", "3m", "5m", "15m"]
    try:
        rows_list = await asyncio.gather(*(fetch_klines(body.symbol, tf, 250) for tf in intervals))
        frames = {tf: analyze_frame(parse_klines(rows), tf) for tf, rows in zip(intervals, rows_list)}
        result = combine(frames, primary=body.interval)
        return AnalyzeResponse(symbol=body.symbol, **result)
    except BinanceMarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {exc}") from exc


@app.get("/trade/demo/status")
async def trade_demo_status(symbol: str = Query(default="BTCUSDT", min_length=5, max_length=20)):
    return await demo_status(symbol)


@app.post("/trade/demo/open")
async def trade_demo_open(
    symbol: str = Query(default="BTCUSDT", min_length=5, max_length=20),
    interval: str = Query(default="1m", pattern="^(1m|3m|5m|15m)$"),
    confirm: bool = Query(default=False),
):
    try:
        return await demo_trade(symbol, interval, confirm)
    except (TradeRejected, RiskRejected) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (BinanceFuturesError, BinanceMarketDataError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/trade/demo/close")
async def trade_demo_close(
    symbol: str = Query(default="BTCUSDT", min_length=5, max_length=20),
    confirm: bool = Query(default=False),
):
    try:
        return await close_demo_position(symbol, confirm)
    except TradeRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BinanceFuturesError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
