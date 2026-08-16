from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import time
from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlencode

import httpx

from .indicators import parse_klines
from .strategy import analyze_frame, combine


BASE_URL = os.getenv("BINANCE_DEMO_FUTURES_URL", "https://demo-fapi.binance.com").rstrip("/")
API_KEY = os.getenv("BINANCE_DEMO_API_KEY", os.getenv("BINANCE_API_KEY", "")).strip()
API_SECRET = os.getenv("BINANCE_DEMO_API_SECRET", os.getenv("BINANCE_API_SECRET", "")).strip()
RECV_WINDOW = int(os.getenv("BINANCE_RECV_WINDOW", "5000"))

SYMBOLS = [s.strip().upper() for s in os.getenv("BOT_ALLOWED_SYMBOLS", "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT").split(",") if s.strip()]
CONFIDENCE_THRESHOLD = float(os.getenv("BOT_MIN_CONFIDENCE", "0.77"))
LEVERAGE = int(os.getenv("BOT_LEVERAGE", "3"))
RISK_PER_TRADE = float(os.getenv("BOT_RISK_PER_TRADE", "0.005"))
MAX_DAILY_LOSS = float(os.getenv("BOT_MAX_DAILY_LOSS", "0.02"))
MAX_MARGIN_FRACTION = float(os.getenv("BOT_MAX_MARGIN_FRACTION", "0.25"))
SCAN_INTERVAL_SEC = int(os.getenv("BOT_SCAN_INTERVAL_SEC", "20"))
COOLDOWN_SEC = int(os.getenv("BOT_COOLDOWN_SEC", "90"))


class BotError(RuntimeError):
    pass


@dataclass
class BotRuntime:
    enabled: bool = False
    started_at: float | None = None
    day_start_balance: float | None = None
    last_scan_at: float | None = None
    last_signal: dict | None = None
    last_trade: dict | None = None
    last_error: str | None = None
    last_closed_symbol: str | None = None
    last_entry_at: float | None = None


runtime = BotRuntime()
_task: asyncio.Task | None = None
_lock = asyncio.Lock()


def _signed_params(params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not API_KEY or not API_SECRET:
        raise BotError("Binance Demo API key/secret are not configured")
    out = dict(params or {})
    out["timestamp"] = int(time.time() * 1000)
    out["recvWindow"] = RECV_WINDOW
    query = urlencode(out, doseq=True)
    out["signature"] = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    return out


async def _request(method: str, path: str, params: dict[str, Any] | None = None, signed: bool = False) -> Any:
    headers = {"X-MBX-APIKEY": API_KEY} if API_KEY else {}
    payload = _signed_params(params) if signed else dict(params or {})
    timeout = httpx.Timeout(12.0, connect=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, f"{BASE_URL}{path}", params=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise BotError(f"Нет связи с Binance Demo: {exc}") from exc
    if response.status_code >= 400:
        try:
            body = response.json()
        except Exception:
            body = response.text
        raise BotError(f"Binance Demo {response.status_code}: {body}")
    return response.json()


async def _klines(symbol: str, interval: str, limit: int = 250) -> list[list]:
    data = await _request("GET", "/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not isinstance(data, list) or len(data) < 60:
        raise BotError(f"Недостаточно свечей {symbol} {interval}")
    return data


async def analyze_demo_symbol(symbol: str, primary: str = "1m") -> dict:
    intervals = ["1m", "3m", "5m", "15m"]
    rows = await asyncio.gather(*(_klines(symbol, tf, 250) for tf in intervals))
    frames = {tf: analyze_frame(parse_klines(item), tf) for tf, item in zip(intervals, rows)}
    result = combine(frames, primary=primary)
    result["symbol"] = symbol
    return result


async def best_suggestion() -> dict:
    results = await asyncio.gather(*(analyze_demo_symbol(s) for s in SYMBOLS), return_exceptions=True)
    clean: list[dict] = []
    errors: dict[str, str] = {}
    for symbol, result in zip(SYMBOLS, results):
        if isinstance(result, Exception):
            errors[symbol] = str(result)
        else:
            clean.append(result)
    if not clean:
        raise BotError(f"Не удалось проанализировать пары: {errors}")
    best = max(clean, key=lambda x: x.get("confidence", 0.0))
    best["eligible"] = bool(best.get("action") in {"BUY", "SELL"} and best.get("confidence", 0.0) >= CONFIDENCE_THRESHOLD)
    best["threshold"] = CONFIDENCE_THRESHOLD
    best["scan_errors"] = errors
    return best


async def _balance() -> dict[str, float]:
    try:
        data = await _request("GET", "/fapi/v3/balance", signed=True)
    except BotError:
        data = await _request("GET", "/fapi/v2/balance", signed=True)
    usdt = next((x for x in data if x.get("asset") == "USDT"), None)
    if not usdt:
        raise BotError("USDT balance not found")
    return {"balance": float(usdt.get("balance", 0.0)), "available_balance": float(usdt.get("availableBalance", 0.0))}


async def _position_mode_is_hedge() -> bool:
    data = await _request("GET", "/fapi/v1/positionSide/dual", signed=True)
    return bool(data.get("dualSidePosition"))


async def _positions() -> list[dict]:
    try:
        data = await _request("GET", "/fapi/v3/positionRisk", signed=True)
    except BotError:
        data = await _request("GET", "/fapi/v2/positionRisk", signed=True)
    out = []
    for p in data:
        amt = float(p.get("positionAmt", 0.0))
        if abs(amt) > 0:
            out.append({"symbol": p.get("symbol"), "position_amt": amt, "entry_price": float(p.get("entryPrice", 0.0)), "mark_price": float(p.get("markPrice", 0.0)), "unrealized_profit": float(p.get("unRealizedProfit", 0.0)), "leverage": int(float(p.get("leverage", 0) or 0))})
    return out


async def _exchange_symbol_info(symbol: str) -> dict:
    info = await _request("GET", "/fapi/v1/exchangeInfo")
    item = next((s for s in info.get("symbols", []) if s.get("symbol") == symbol), None)
    if not item:
        raise BotError(f"Символ {symbol} не найден")
    return item


def _floor_to_step(value: float, step: str) -> float:
    d = Decimal(str(value)); s = Decimal(step)
    return float((d / s).to_integral_value(rounding=ROUND_DOWN) * s)


def _round_to_tick(value: float, tick: str) -> float:
    d = Decimal(str(value)); t = Decimal(tick)
    return float((d / t).to_integral_value(rounding=ROUND_HALF_UP) * t)


async def _quantity(symbol: str, notional: float, price: float) -> float:
    item = await _exchange_symbol_info(symbol)
    filters = {f.get("filterType"): f for f in item.get("filters", [])}
    lot = filters.get("MARKET_LOT_SIZE") or filters.get("LOT_SIZE")
    if not lot:
        raise BotError("LOT_SIZE filter missing")
    qty = _floor_to_step(notional / price, lot["stepSize"])
    if qty < float(lot["minQty"]):
        raise BotError(f"Размер позиции меньше minQty для {symbol}")
    return qty


async def _rounded_trigger(symbol: str, price: float) -> float:
    item = await _exchange_symbol_info(symbol)
    f = next((x for x in item.get("filters", []) if x.get("filterType") == "PRICE_FILTER"), None)
    if not f:
        return price
    return _round_to_tick(price, f["tickSize"])


async def _set_leverage(symbol: str) -> None:
    await _request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": LEVERAGE}, signed=True)


async def _market_order(symbol: str, side: str, quantity: float, reduce_only: bool = False) -> dict:
    params: dict[str, Any] = {"symbol": symbol, "side": side, "type": "MARKET", "quantity": format(Decimal(str(quantity)).normalize(), "f"), "newOrderRespType": "RESULT"}
    if reduce_only:
        params["reduceOnly"] = "true"
    return await _request("POST", "/fapi/v1/order", params, signed=True)


async def _algo_close_order(symbol: str, side: str, kind: str, trigger_price: float) -> dict:
    params = {"algoType": "CONDITIONAL", "symbol": symbol, "side": side, "type": kind, "triggerPrice": format(Decimal(str(trigger_price)).normalize(), "f"), "closePosition": "true", "workingType": "MARK_PRICE", "priceProtect": "TRUE"}
    return await _request("POST", "/fapi/v1/algoOrder", params, signed=True)


async def _cancel_algo_orders(symbol: str) -> None:
    try:
        await _request("DELETE", "/fapi/v1/algoOpenOrders", {"symbol": symbol}, signed=True)
    except BotError as exc:
        if "Unknown order" not in str(exc) and "not found" not in str(exc).lower():
            raise


async def _open_algo_orders(symbol: str) -> list[dict]:
    data = await _request("GET", "/fapi/v1/openAlgoOrders", {"symbol": symbol}, signed=True)
    return data if isinstance(data, list) else []


async def _emergency_close(symbol: str) -> None:
    positions = await _positions(); p = next((x for x in positions if x["symbol"] == symbol), None)
    if not p:
        return
    side = "SELL" if p["position_amt"] > 0 else "BUY"
    await _market_order(symbol, side, abs(p["position_amt"]), reduce_only=True)
    await _cancel_algo_orders(symbol)


async def execute_signal(signal: dict) -> dict:
    symbol = signal["symbol"]; side = signal["action"]
    if side not in {"BUY", "SELL"}: raise BotError("Signal is HOLD")
    if signal.get("confidence", 0.0) < CONFIDENCE_THRESHOLD: raise BotError("Confidence below threshold")
    if signal.get("stop_loss") is None or signal.get("take_profit") is None: raise BotError("Signal has no SL/TP")
    if await _position_mode_is_hedge(): raise BotError("Hedge Mode включен. Нужен One-way Mode.")
    current_positions = await _positions()
    if current_positions: raise BotError("Уже есть открытая позиция — второй вход заблокирован")
    bal = await _balance()
    if runtime.day_start_balance is None: runtime.day_start_balance = bal["balance"]
    if runtime.day_start_balance > 0 and bal["balance"] <= runtime.day_start_balance * (1 - MAX_DAILY_LOSS): raise BotError("Достигнут дневной лимит убытка; AUTO остановлен")
    entry = float(signal["entry"]); stop = float(signal["stop_loss"]); stop_pct = abs(entry - stop) / entry
    if stop_pct < 0.0015 or stop_pct > 0.03: raise BotError(f"SL вне допустимого диапазона: {stop_pct:.3%}")
    risk_usdt = bal["available_balance"] * RISK_PER_TRADE
    notional_by_risk = risk_usdt / stop_pct
    max_notional = bal["available_balance"] * MAX_MARGIN_FRACTION * LEVERAGE
    notional = min(notional_by_risk, max_notional)
    qty = await _quantity(symbol, notional, entry)
    await _cancel_algo_orders(symbol); await _set_leverage(symbol)
    market = await _market_order(symbol, side, qty)
    exit_side = "SELL" if side == "BUY" else "BUY"
    stop_trigger = await _rounded_trigger(symbol, float(signal["stop_loss"])); tp_trigger = await _rounded_trigger(symbol, float(signal["take_profit"]))
    try:
        sl_order = await _algo_close_order(symbol, exit_side, "STOP_MARKET", stop_trigger)
        tp_order = await _algo_close_order(symbol, exit_side, "TAKE_PROFIT_MARKET", tp_trigger)
        active = await _open_algo_orders(symbol)
        if len(active) < 2: raise BotError("Binance не подтвердил два защитных algo-ордера")
    except Exception:
        await _emergency_close(symbol); raise
    trade = {"symbol": symbol, "side": side, "confidence_score": signal["confidence"], "quantity": qty, "leverage": LEVERAGE, "estimated_notional_usdt": round(notional, 4), "risk_budget_usdt": round(risk_usdt, 4), "stop_loss": stop_trigger, "take_profit": tp_trigger, "entry_order": market, "stop_order": sl_order, "take_profit_order": tp_order, "opened_at": time.time()}
    runtime.last_trade = trade; runtime.last_entry_at = time.time(); return trade


async def _housekeeping_after_close() -> None:
    if not runtime.last_trade: return
    symbol = runtime.last_trade.get("symbol")
    if not symbol: return
    positions = await _positions()
    if not any(p["symbol"] == symbol for p in positions):
        await _cancel_algo_orders(symbol); runtime.last_closed_symbol = symbol


async def _loop() -> None:
    while runtime.enabled:
        try:
            runtime.last_scan_at = time.time(); bal = await _balance()
            if runtime.day_start_balance is None: runtime.day_start_balance = bal["balance"]
            if runtime.day_start_balance > 0 and bal["balance"] <= runtime.day_start_balance * (1 - MAX_DAILY_LOSS):
                runtime.last_error = "Достигнут дневной лимит убытка. AUTO остановлен."; runtime.enabled = False; break
            positions = await _positions()
            if positions:
                runtime.last_signal = {"action": "WAIT_POSITION", "positions": positions}
            else:
                await _housekeeping_after_close(); suggestion = await best_suggestion(); runtime.last_signal = suggestion
                cooldown_ok = runtime.last_entry_at is None or (time.time() - runtime.last_entry_at) >= COOLDOWN_SEC
                if suggestion.get("eligible") and cooldown_ok: await execute_signal(suggestion)
            runtime.last_error = None
        except Exception as exc:
            runtime.last_error = str(exc)
            if "дневной лимит" in runtime.last_error.lower() or "Hedge Mode" in runtime.last_error:
                runtime.enabled = False; break
        await asyncio.sleep(max(5, SCAN_INTERVAL_SEC))


async def start_bot() -> dict:
    global _task
    async with _lock:
        if runtime.enabled and _task and not _task.done(): return await bot_status()
        if not API_KEY or not API_SECRET: raise BotError("API keys missing")
        if LEVERAGE != 3: raise BotError("Для текущего профиля BOT_LEVERAGE должен быть 3")
        if CONFIDENCE_THRESHOLD < 0.77: raise BotError("Порог AUTO не может быть ниже 0.77 в текущей версии")
        if await _position_mode_is_hedge(): raise BotError("Переключи Binance Demo Futures в One-way Mode перед запуском AUTO")
        bal = await _balance(); runtime.enabled = True; runtime.started_at = time.time(); runtime.day_start_balance = bal["balance"]; runtime.last_error = None
        _task = asyncio.create_task(_loop(), name="scalping-auto-demo"); return await bot_status()


async def stop_bot(close_position: bool = False) -> dict:
    global _task
    runtime.enabled = False
    if _task and not _task.done():
        _task.cancel()
        try: await _task
        except asyncio.CancelledError: pass
    _task = None
    if close_position:
        for p in await _positions(): await _emergency_close(p["symbol"])
    return await bot_status()


async def bot_status() -> dict:
    try:
        bal = await _balance() if API_KEY and API_SECRET else None; positions = await _positions() if API_KEY and API_SECRET else []
    except Exception as exc:
        bal = None; positions = []; runtime.last_error = str(exc)
    return {"mode":"DEMO","auto_enabled":runtime.enabled,"confidence_threshold":CONFIDENCE_THRESHOLD,"confidence_note":"Это внутренний score стратегии, а не статистически гарантированная вероятность выигрыша.","leverage":LEVERAGE,"risk_per_trade":RISK_PER_TRADE,"max_daily_loss":MAX_DAILY_LOSS,"scan_interval_sec":SCAN_INTERVAL_SEC,"symbols":SYMBOLS,"balance":bal,"positions":positions,"runtime":asdict(runtime)}