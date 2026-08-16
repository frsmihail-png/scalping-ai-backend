import asyncio
import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from . import auto_demo_bot as bot_engine
from .auto_demo_bot import BotError, best_suggestion, bot_status, start_bot, stop_bot
from .binance_client import BinanceMarketDataError, fetch_klines
from .demo_status import DemoStatusError, get_demo_status
from .indicators import parse_klines
from .models import AnalyzeRequest, AnalyzeResponse
from .panel import PANEL_HTML
from .strategy import analyze_frame, combine

load_dotenv()

bot_engine.CONFIDENCE_THRESHOLD = 0.77
bot_engine.SCAN_INTERVAL_SEC = 10

app = FastAPI(title="Scalping AI API", version="0.5.3")

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
    return {"name": "Scalping AI API", "version": "0.5.3", "mode": "DEMO_AUTO", "panel": "/panel"}

@app.get("/panel", response_class=HTMLResponse, include_in_schema=False)
async def panel():
    return HTMLResponse(content=PANEL_HTML, status_code=200)

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/market/live")
async def live_market(symbol: str = Query(default="BTCUSDT", min_length=5, max_length=20)):
    symbol = symbol.upper().strip()
    base = "https://fapi.binance.com"
    timeout = httpx.Timeout(5.0, connect=3.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            ticker_req = client.get(f"{base}/fapi/v1/ticker/bookTicker", params={"symbol": symbol})
            price_req = client.get(f"{base}/fapi/v1/ticker/price", params={"symbol": symbol})
            depth_req = client.get(f"{base}/fapi/v1/depth", params={"symbol": symbol, "limit": 10})
            ticker_res, price_res, depth_res = await asyncio.gather(ticker_req, price_req, depth_req)
        for response in (ticker_res, price_res, depth_res):
            if response.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Binance LIVE {response.status_code}: {response.text}")
        ticker = ticker_res.json(); price = price_res.json(); depth = depth_res.json()
        return {"source":"BINANCE_LIVE_USDM_REST_SNAPSHOT","symbol":symbol,"price":float(price.get("price",0.0)),"bid":float(ticker.get("bidPrice",0.0)),"bid_qty":float(ticker.get("bidQty",0.0)),"ask":float(ticker.get("askPrice",0.0)),"ask_qty":float(ticker.get("askQty",0.0)),"bids":[[float(p),float(q)] for p,q in depth.get("bids",[])],"asks":[[float(p),float(q)] for p,q in depth.get("asks",[])],"last_update_id":depth.get("lastUpdateId")}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ошибка LIVE Binance Futures: {exc}") from exc

@app.get("/binance/demo/status")
async def binance_demo_status(symbol: str = Query(default="BTCUSDT", min_length=5, max_length=20)):
    try:
        return await get_demo_status(symbol)
    except DemoStatusError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ошибка проверки Binance Demo: {exc}") from exc

@app.get("/bot/suggestion")
async def bot_suggestion():
    try:
        return await best_suggestion()
    except BotError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@app.get("/bot/status")
async def get_bot_status():
    return await bot_status()

@app.post("/bot/start", summary="AUTO START")
async def bot_start(confirm: bool = Query(default=False)):
    if not confirm:
        raise HTTPException(status_code=409, detail="Для запуска DEMO AUTO укажи confirm=true")
    try:
        return await start_bot()
    except BotError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@app.post("/bot/stop", summary="STOP AUTO")
async def bot_stop(close_position: bool = Query(default=False)):
    try:
        return await stop_bot(close_position=close_position)
    except BotError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@app.post("/bot/emergency-stop", summary="EMERGENCY STOP — запретить новые входы")
async def bot_emergency_stop():
    try:
        result = await stop_bot(close_position=False)
        return {"ok":True,"action":"EMERGENCY_STOP","message":"AUTO остановлен. Новые сделки открываться не будут. Открытые позиции оставлены под существующими SL/TP.","status":result}
    except BotError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@app.post("/bot/close-all", summary="CLOSE ALL — закрыть все сделки")
async def bot_close_all(confirm: bool = Query(default=False)):
    if not confirm:
        raise HTTPException(status_code=409, detail="Для закрытия всех DEMO-позиций укажи confirm=true")
    try:
        result = await stop_bot(close_position=True)
        return {"ok":True,"action":"CLOSE_ALL","message":"AUTO остановлен. Команда закрытия всех открытых DEMO-позиций выполнена.","status":result}
    except BotError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

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
