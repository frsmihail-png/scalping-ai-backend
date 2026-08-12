import asyncio
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .binance_client import BinanceMarketDataError, fetch_klines
from .demo_status import DemoStatusError, get_demo_status
from .indicators import parse_klines
from .models import AnalyzeRequest, AnalyzeResponse
from .strategy import analyze_frame, combine

load_dotenv()

app = FastAPI(title="Scalping AI API", version="0.2.1")

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
    return {"name": "Scalping AI API", "version": "0.2.1", "mode": "paper+demo-check"}


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/binance/demo/status")
async def binance_demo_status(symbol: str = Query(default="BTCUSDT", min_length=5, max_length=20)):
    try:
        return await get_demo_status(symbol)
    except DemoStatusError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ошибка проверки Binance Demo: {exc}") from exc


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(body: AnalyzeRequest):
    intervals = ["1m", "3m", "5m", "15m"]
    try:
        rows_list = await asyncio.gather(*(fetch_klines(body.symbol, tf, 250) for tf in intervals))
        frames = {
            tf: analyze_frame(parse_klines(rows), tf)
            for tf, rows in zip(intervals, rows_list)
        }
        result = combine(frames, primary=body.interval)
        return AnalyzeResponse(symbol=body.symbol, **result)
    except BinanceMarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {exc}") from exc
