from __future__ import annotations

import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

import httpx


BASE_URL = os.getenv("BINANCE_DEMO_FUTURES_URL", "https://demo-fapi.binance.com").rstrip("/")
API_KEY = os.getenv("BINANCE_DEMO_API_KEY", os.getenv("BINANCE_API_KEY", "")).strip()
API_SECRET = os.getenv("BINANCE_DEMO_API_SECRET", os.getenv("BINANCE_API_SECRET", "")).strip()
RECV_WINDOW = int(os.getenv("BINANCE_RECV_WINDOW", "5000"))


class DemoStatusError(RuntimeError):
    pass


def _signed_params(params: dict | None = None) -> dict:
    if not API_KEY or not API_SECRET:
        raise DemoStatusError("Binance Demo API key/secret are not configured")
    out = dict(params or {})
    out["timestamp"] = int(time.time() * 1000)
    out["recvWindow"] = RECV_WINDOW
    query = urlencode(out)
    out["signature"] = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    return out


async def _signed_get(path: str, params: dict | None = None):
    headers = {"X-MBX-APIKEY": API_KEY}
    timeout = httpx.Timeout(12.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"{BASE_URL}{path}", params=_signed_params(params), headers=headers)
    if response.status_code >= 400:
        try:
            body = response.json()
        except Exception:
            body = response.text
        raise DemoStatusError(f"Binance Demo {response.status_code}: {body}")
    return response.json()


def _num(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _trigger_price(order: dict) -> float:
    for key in ("triggerPrice", "stopPrice", "activatePrice", "price"):
        value = _num(order.get(key))
        if value > 0:
            return value
    return 0.0


async def get_demo_status(symbol: str = "BTCUSDT") -> dict:
    symbol = symbol.upper()
    result = {
        "mode": "DEMO",
        "base_url": BASE_URL,
        "credentials_present": bool(API_KEY and API_SECRET),
        "symbol": symbol,
    }
    if not result["credentials_present"]:
        return result

    # Binance has used both v2 and v3 account endpoints over time; try v3 first.
    try:
        balances = await _signed_get("/fapi/v3/balance")
    except DemoStatusError:
        balances = await _signed_get("/fapi/v2/balance")

    usdt = next((x for x in balances if x.get("asset") == "USDT"), None)
    result["usdt"] = {
        "balance": float(usdt.get("balance", 0)) if usdt else 0.0,
        "available_balance": float(usdt.get("availableBalance", 0)) if usdt else 0.0,
    }

    # Restore protection information directly from Binance. This survives a Render
    # restart/deploy even when the in-memory runtime.last_trade is empty.
    try:
        algo_orders = await _signed_get("/fapi/v1/algoOpenOrders", {"symbol": symbol})
        if not isinstance(algo_orders, list):
            algo_orders = []
    except DemoStatusError as exc:
        algo_orders = []
        result["protection_error"] = str(exc)

    tp = 0.0
    sl = 0.0
    protection_orders: list[dict] = []
    for order in algo_orders:
        kind = str(order.get("type") or order.get("orderType") or "").upper()
        trigger = _trigger_price(order)
        compact = {
            "type": kind,
            "side": str(order.get("side", "")).upper(),
            "trigger_price": trigger,
            "status": order.get("status"),
            "algo_id": order.get("algoId") or order.get("clientAlgoId"),
            "close_position": order.get("closePosition"),
        }
        protection_orders.append(compact)
        if "TAKE_PROFIT" in kind and trigger > 0:
            tp = trigger
        elif "STOP" in kind and "TAKE_PROFIT" not in kind and trigger > 0:
            sl = trigger

    result["protection"] = {
        "take_profit": tp,
        "stop_loss": sl,
        "protected": bool(tp > 0 and sl > 0),
        "open_algo_orders": protection_orders,
        "source": "BINANCE_DEMO_ALGO_OPEN_ORDERS",
    }
    return result
