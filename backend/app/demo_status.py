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
    for key in ("triggerPrice", "stopPrice", "activatePrice", "activationPrice", "price"):
        value = _num(order.get(key))
        if value > 0:
            return value
    return 0.0


def _normalize_orders(data) -> list[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("orders", "data", "rows", "list"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        # Some environments return one order object directly.
        if data.get("symbol") and (data.get("type") or data.get("orderType")):
            return [data]
    return []


async def _load_protection_orders(symbol: str) -> tuple[list[dict], str, list[str]]:
    """Query protection orders using current and legacy Binance Demo variants.

    Binance Demo has changed conditional-order endpoints over time. We try the
    dedicated algo endpoint first, then compatible fallbacks. This also lets
    the UI recover TP/SL after a Render restart because the source of truth is
    Binance, not runtime.last_trade.
    """
    attempts: list[str] = []
    candidates = [
        ("/fapi/v1/algoOpenOrders", {"symbol": symbol}),
        ("/fapi/v1/openAlgoOrders", {"symbol": symbol}),
        ("/fapi/v1/openOrders", {"symbol": symbol}),
    ]
    combined: list[dict] = []
    source = ""
    seen: set[str] = set()

    for path, params in candidates:
        try:
            data = await _signed_get(path, params)
            orders = _normalize_orders(data)
            attempts.append(f"{path}:ok:{len(orders)}")
            if orders and not source:
                source = path
            for order in orders:
                key = str(order.get("algoId") or order.get("orderId") or order.get("clientAlgoId") or order)
                if key not in seen:
                    seen.add(key)
                    combined.append(order)
        except DemoStatusError as exc:
            attempts.append(f"{path}:error:{exc}")

    return combined, source or "NO_OPEN_ORDER_SOURCE", attempts


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

    try:
        balances = await _signed_get("/fapi/v3/balance")
    except DemoStatusError:
        balances = await _signed_get("/fapi/v2/balance")

    usdt = next((x for x in balances if x.get("asset") == "USDT"), None)
    result["usdt"] = {
        "balance": float(usdt.get("balance", 0)) if usdt else 0.0,
        "available_balance": float(usdt.get("availableBalance", 0)) if usdt else 0.0,
    }

    algo_orders, source, attempts = await _load_protection_orders(symbol)

    tp = 0.0
    sl = 0.0
    protection_orders: list[dict] = []
    for order in algo_orders:
        kind = str(order.get("type") or order.get("orderType") or order.get("origType") or "").upper()
        trigger = _trigger_price(order)
        status = str(order.get("status") or order.get("algoStatus") or "").upper()
        # Ignore clearly finished/cancelled rows if a fallback endpoint returns history.
        if status in {"FILLED", "CANCELED", "CANCELLED", "EXPIRED", "REJECTED"}:
            continue
        compact = {
            "type": kind,
            "side": str(order.get("side", "")).upper(),
            "trigger_price": trigger,
            "status": status or order.get("status"),
            "algo_id": order.get("algoId") or order.get("clientAlgoId") or order.get("orderId"),
            "close_position": order.get("closePosition"),
            "reduce_only": order.get("reduceOnly"),
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
        "source": source,
        "query_attempts": attempts,
    }
    if tp <= 0 or sl <= 0:
        result["protection_warning"] = "Открытая защита TP/SL не обнаружена полностью. Проверь условные ордера Binance Demo."
    return result
