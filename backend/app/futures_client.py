from __future__ import annotations

import hashlib
import hmac
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any
from urllib.parse import urlencode

import httpx

from .config import TradingSettings


class BinanceFuturesError(RuntimeError):
    pass


class BinanceFuturesClient:
    def __init__(self, cfg: TradingSettings):
        self.cfg = cfg
        self.base_url = cfg.demo_base_url
        self.timeout = httpx.Timeout(12.0, connect=5.0)

    def _credentials(self) -> None:
        if not self.cfg.api_key or not self.cfg.api_secret:
            raise BinanceFuturesError("Не заданы BINANCE_DEMO_API_KEY / BINANCE_DEMO_API_SECRET")

    async def _request(self, method: str, path: str, params: dict[str, Any] | None = None, signed: bool = False) -> Any:
        params = dict(params or {})
        headers: dict[str, str] = {}
        if signed:
            self._credentials()
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = self.cfg.recv_window
            query = urlencode(params, doseq=True)
            params["signature"] = hmac.new(self.cfg.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            headers["X-MBX-APIKEY"] = self.cfg.api_key
        elif self.cfg.api_key:
            headers["X-MBX-APIKEY"] = self.cfg.api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, f"{self.base_url}{path}", params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise BinanceFuturesError(f"Нет связи с Binance Futures Demo: {exc}") from exc

        if response.status_code >= 400:
            try:
                payload = response.json()
                message = payload.get("msg", str(payload))
                code = payload.get("code")
            except Exception:
                message, code = response.text, None
            raise BinanceFuturesError(f"Binance Futures {response.status_code} ({code}): {message}")
        return response.json()

    async def ping(self) -> bool:
        await self._request("GET", "/fapi/v1/ping")
        return True

    async def balance(self) -> dict[str, float]:
        data = await self._request("GET", "/fapi/v3/balance", signed=True)
        usdt = next((x for x in data if x.get("asset") == "USDT"), None)
        if not usdt:
            raise BinanceFuturesError("На DEMO Futures не найден баланс USDT")
        return {
            "balance": float(usdt.get("balance", 0)),
            "available_balance": float(usdt.get("availableBalance", 0)),
            "cross_wallet_balance": float(usdt.get("crossWalletBalance", 0)),
        }

    async def position(self, symbol: str) -> dict[str, float]:
        data = await self._request("GET", "/fapi/v3/positionRisk", {"symbol": symbol}, signed=True)
        item = data[0] if isinstance(data, list) and data else {}
        return {
            "position_amt": float(item.get("positionAmt", 0)),
            "entry_price": float(item.get("entryPrice", 0)),
            "mark_price": float(item.get("markPrice", 0)),
            "unrealized_profit": float(item.get("unRealizedProfit", 0)),
            "leverage": float(item.get("leverage", 0)),
        }

    async def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        return await self._request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage}, signed=True)

    async def exchange_info(self) -> dict[str, Any]:
        return await self._request("GET", "/fapi/v1/exchangeInfo")

    async def quantity_for_notional(self, symbol: str, notional: float, price: float) -> float:
        info = await self.exchange_info()
        symbol_info = next((s for s in info.get("symbols", []) if s.get("symbol") == symbol), None)
        if not symbol_info:
            raise BinanceFuturesError(f"Символ {symbol} не найден на Binance Futures")
        lot = next((f for f in symbol_info.get("filters", []) if f.get("filterType") == "LOT_SIZE"), None)
        if not lot:
            raise BinanceFuturesError(f"LOT_SIZE для {symbol} не найден")
        step = Decimal(str(lot["stepSize"]))
        min_qty = Decimal(str(lot["minQty"]))
        raw = Decimal(str(notional)) / Decimal(str(price))
        qty = (raw / step).to_integral_value(rounding=ROUND_DOWN) * step
        if qty < min_qty:
            raise BinanceFuturesError(f"Размер позиции {qty} меньше minQty {min_qty} для {symbol}")
        return float(qty)

    async def market_order(self, symbol: str, side: str, quantity: float, reduce_only: bool = False) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": self._fmt(quantity),
            "newOrderRespType": "RESULT",
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        return await self._request("POST", "/fapi/v1/order", params, signed=True)

    async def close_position(self, symbol: str) -> dict[str, Any] | None:
        pos = await self.position(symbol)
        amount = pos["position_amt"]
        if amount == 0:
            return None
        side = "SELL" if amount > 0 else "BUY"
        return await self.market_order(symbol, side, abs(amount), reduce_only=True)

    @staticmethod
    def _fmt(value: float) -> str:
        return format(Decimal(str(value)).normalize(), "f")
