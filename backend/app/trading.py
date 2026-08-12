from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import date

from .binance_client import fetch_klines
from .config import settings
from .futures_client import BinanceFuturesClient, BinanceFuturesError
from .indicators import parse_klines
from .risk import RiskRejected, build_position_plan
from .strategy import analyze_frame, combine


class TradeRejected(RuntimeError):
    pass


_lock = asyncio.Lock()
_day = date.today()
_day_start_balance: float | None = None
_consecutive_losses = 0


async def analyze_symbol(symbol: str, interval: str = "1m") -> dict:
    intervals = ["1m", "3m", "5m", "15m"]
    rows_list = await asyncio.gather(*(fetch_klines(symbol, tf, 250) for tf in intervals))
    frames = {tf: analyze_frame(parse_klines(rows), tf) for tf, rows in zip(intervals, rows_list)}
    return combine(frames, primary=interval)


async def demo_trade(symbol: str, interval: str = "1m", confirm: bool = False) -> dict:
    global _day, _day_start_balance

    if settings.validate():
        raise TradeRejected("; ".join(settings.validate()))
    if not settings.enabled:
        raise TradeRejected("DEMO-торговля выключена. Установи ENABLE_DEMO_TRADING=true только после добавления DEMO API ключей.")
    if not confirm:
        raise TradeRejected("Для отправки DEMO-ордера требуется confirm=true")

    symbol = symbol.upper().replace("/", "")
    if symbol not in settings.allowed_symbols:
        raise TradeRejected(f"{symbol} не входит в BOT_ALLOWED_SYMBOLS")

    async with _lock:
        client = BinanceFuturesClient(settings)
        balance = await client.balance()
        available = balance["available_balance"]
        today = date.today()
        if today != _day or _day_start_balance is None:
            _day = today
            _day_start_balance = balance["balance"]

        if _day_start_balance and balance["balance"] <= _day_start_balance * (1 - settings.max_daily_loss):
            raise TradeRejected("Достигнут дневной лимит убытка. Новые сделки заблокированы до следующего дня.")
        if _consecutive_losses >= settings.max_consecutive_losses:
            raise TradeRejected("Достигнут лимит последовательных убыточных сделок. Требуется ручной сброс/разбор.")

        existing = await client.position(symbol)
        if abs(existing["position_amt"]) > 0:
            raise TradeRejected(f"По {symbol} уже есть открытая позиция; повторный вход заблокирован")

        signal = await analyze_symbol(symbol, interval)
        if signal["action"] not in {"BUY", "SELL"}:
            raise TradeRejected("Стратегия сейчас дает HOLD — ордер не отправлен")
        if signal["confidence"] < settings.min_confidence:
            raise TradeRejected(f"Confidence {signal['confidence']:.2%} ниже порога {settings.min_confidence:.2%}")
        if signal["stop_loss"] is None or signal["take_profit"] is None:
            raise TradeRejected("Стратегия не рассчитала SL/TP")

        plan = build_position_plan(
            available_balance=available,
            entry=signal["entry"],
            stop_loss=signal["stop_loss"],
            leverage=settings.leverage,
            risk_fraction=settings.risk_per_trade,
            max_margin_fraction=settings.max_margin_fraction,
        )
        qty = await client.quantity_for_notional(symbol, plan.notional_usdt, signal["entry"])
        await client.set_leverage(symbol, settings.leverage)
        order = await client.market_order(symbol, signal["action"], qty)

        return {
            "mode": "DEMO",
            "symbol": symbol,
            "signal": signal,
            "risk": asdict(plan),
            "quantity": qty,
            "leverage": settings.leverage,
            "order": order,
            "note": "DEMO market entry placed. Protective exits are managed by /trade/demo/close until server-side SL/TP is enabled after exchange validation.",
        }


async def close_demo_position(symbol: str, confirm: bool = False) -> dict:
    if settings.mode != "DEMO":
        raise TradeRejected("LIVE режим заблокирован")
    if not settings.enabled:
        raise TradeRejected("DEMO-торговля выключена")
    if not confirm:
        raise TradeRejected("Для закрытия DEMO-позиции требуется confirm=true")
    client = BinanceFuturesClient(settings)
    result = await client.close_position(symbol.upper().replace("/", ""))
    return {"mode": "DEMO", "symbol": symbol.upper(), "closed": result is not None, "order": result}


async def demo_status(symbol: str = "BTCUSDT") -> dict:
    client = BinanceFuturesClient(settings)
    base = {
        "mode": settings.mode,
        "enabled": settings.enabled,
        "leverage": settings.leverage,
        "risk_per_trade": settings.risk_per_trade,
        "max_daily_loss": settings.max_daily_loss,
        "min_confidence": settings.min_confidence,
        "allowed_symbols": sorted(settings.allowed_symbols),
        "config_errors": settings.validate(),
        "credentials_present": bool(settings.api_key and settings.api_secret),
    }
    if not settings.api_key or not settings.api_secret:
        return base
    try:
        base["balance"] = await client.balance()
        base["position"] = await client.position(symbol.upper().replace("/", ""))
    except BinanceFuturesError as exc:
        base["exchange_error"] = str(exc)
    return base
