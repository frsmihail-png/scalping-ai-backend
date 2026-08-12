import os
from typing import List

import httpx


BASE_URL = os.getenv("BINANCE_MARKET_DATA_URL", "https://data-api.binance.vision").rstrip("/")


class BinanceMarketDataError(RuntimeError):
    pass


async def fetch_klines(symbol: str, interval: str, limit: int = 250) -> List[list]:
    url = f"{BASE_URL}/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    timeout = httpx.Timeout(10.0, connect=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params)
    except httpx.HTTPError as exc:
        raise BinanceMarketDataError(f"Нет связи с Binance: {exc}") from exc

    if response.status_code != 200:
        try:
            payload = response.json()
            message = payload.get("msg", response.text)
        except Exception:
            message = response.text
        raise BinanceMarketDataError(f"Binance API {response.status_code}: {message}")

    data = response.json()
    if not isinstance(data, list) or len(data) < 60:
        raise BinanceMarketDataError("Binance вернул недостаточно свечей для анализа")
    return data
