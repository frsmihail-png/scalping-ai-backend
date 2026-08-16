from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import auto_demo_bot_v2 as bot
from .live_pnl_ui import LIVE_PNL_SCRIPT

EPS = 1e-10


@dataclass
class ClosedTrade:
    symbol: str
    side: str
    opened_at: int
    closed_at: int
    fills: int
    realized_pnl: float
    commission: float
    net_pnl: float
    duration_sec: float


def _num(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


async def _user_trades(symbol: str, limit: int = 1000) -> list[dict]:
    data = await bot._request(
        "GET",
        "/fapi/v1/userTrades",
        {"symbol": symbol, "limit": max(1, min(int(limit), 1000))},
        signed=True,
    )
    return data if isinstance(data, list) else []


def _reconstruct_closed_trades(symbol: str, fills: list[dict]) -> tuple[list[ClosedTrade], dict | None]:
    fills = sorted(fills, key=lambda x: (int(x.get("time", 0) or 0), int(x.get("id", 0) or 0)))
    position = 0.0
    cycle: dict | None = None
    closed: list[ClosedTrade] = []

    for fill in fills:
        qty = abs(_num(fill.get("qty")))
        if qty <= EPS:
            continue
        side = str(fill.get("side", "")).upper()
        signed_qty = qty if side == "BUY" else -qty
        ts = int(fill.get("time", 0) or 0)
        commission = _num(fill.get("commission"))
        commission_asset = str(fill.get("commissionAsset", "USDT") or "USDT").upper()
        commission_usdt = commission if commission_asset == "USDT" else 0.0
        realized = _num(fill.get("realizedPnl"))

        if cycle is None:
            cycle = {
                "side": "LONG" if signed_qty > 0 else "SHORT",
                "opened_at": ts,
                "fills": 0,
                "realized_pnl": 0.0,
                "commission": 0.0,
                "non_usdt_commission": {},
            }

        cycle["fills"] += 1
        cycle["realized_pnl"] += realized
        cycle["commission"] += commission_usdt
        if commission_asset != "USDT" and commission:
            cycle["non_usdt_commission"][commission_asset] = cycle["non_usdt_commission"].get(commission_asset, 0.0) + commission

        new_position = position + signed_qty

        if abs(new_position) <= EPS:
            gross = float(cycle["realized_pnl"])
            fees = float(cycle["commission"])
            net = gross - fees
            closed.append(
                ClosedTrade(
                    symbol=symbol,
                    side=str(cycle["side"]),
                    opened_at=int(cycle["opened_at"]),
                    closed_at=ts,
                    fills=int(cycle["fills"]),
                    realized_pnl=gross,
                    commission=fees,
                    net_pnl=net,
                    duration_sec=max(0.0, (ts - int(cycle["opened_at"])) / 1000.0),
                )
            )
            cycle = None
            position = 0.0
        else:
            if position != 0 and (position > 0) != (new_position > 0):
                gross = float(cycle["realized_pnl"])
                fees = float(cycle["commission"])
                net = gross - fees
                closed.append(
                    ClosedTrade(
                        symbol=symbol,
                        side=str(cycle["side"]),
                        opened_at=int(cycle["opened_at"]),
                        closed_at=ts,
                        fills=int(cycle["fills"]),
                        realized_pnl=gross,
                        commission=fees,
                        net_pnl=net,
                        duration_sec=max(0.0, (ts - int(cycle["opened_at"])) / 1000.0),
                    )
                )
                cycle = {
                    "side": "LONG" if new_position > 0 else "SHORT",
                    "opened_at": ts,
                    "fills": 0,
                    "realized_pnl": 0.0,
                    "commission": 0.0,
                    "non_usdt_commission": {},
                }
            position = new_position

    open_cycle = None
    if cycle is not None and abs(position) > EPS:
        open_cycle = {
            "symbol": symbol,
            "side": "LONG" if position > 0 else "SHORT",
            "position_qty": abs(position),
            "opened_at": int(cycle["opened_at"]),
            "fills": int(cycle["fills"]),
            "realized_pnl_so_far": round(float(cycle["realized_pnl"]), 8),
            "commission_so_far": round(float(cycle["commission"]), 8),
        }
    return closed, open_cycle


def _metrics(trades: list[ClosedTrade]) -> dict:
    wins = [t for t in trades if t.net_pnl > EPS]
    losses = [t for t in trades if t.net_pnl < -EPS]
    breakeven = len(trades) - len(wins) - len(losses)
    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = sum(t.net_pnl for t in losses)
    net_pnl = sum(t.net_pnl for t in trades)
    realized = sum(t.realized_pnl for t in trades)
    commissions = sum(t.commission for t in trades)
    profit_factor = None if abs(gross_loss) <= EPS else gross_profit / abs(gross_loss)
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": breakeven,
        "win_rate_pct": round((len(wins) / len(trades) * 100.0) if trades else 0.0, 2),
        "net_pnl_usdt": round(net_pnl, 8),
        "realized_pnl_before_commission_usdt": round(realized, 8),
        "commissions_usdt": round(commissions, 8),
        "avg_win_usdt": round((gross_profit / len(wins)) if wins else 0.0, 8),
        "avg_loss_usdt": round((gross_loss / len(losses)) if losses else 0.0, 8),
        "profit_factor": None if profit_factor is None else round(profit_factor, 4),
        "expectancy_usdt_per_trade": round((net_pnl / len(trades)) if trades else 0.0, 8),
        "avg_duration_sec": round((sum(t.duration_sec for t in trades) / len(trades)) if trades else 0.0, 1),
    }


async def performance_report(limit_per_symbol: int = 1000, recent: int = 20) -> dict:
    all_closed: list[ClosedTrade] = []
    by_symbol: dict[str, dict] = {}
    open_cycles: list[dict] = []
    errors: dict[str, str] = {}

    for symbol in bot.SYMBOLS:
        try:
            fills = await _user_trades(symbol, limit_per_symbol)
            closed, open_cycle = _reconstruct_closed_trades(symbol, fills)
            all_closed.extend(closed)
            by_symbol[symbol] = _metrics(closed)
            by_symbol[symbol]["fills_loaded"] = len(fills)
            if open_cycle:
                open_cycles.append(open_cycle)
        except Exception as exc:
            errors[symbol] = str(exc)
            by_symbol[symbol] = _metrics([])
            by_symbol[symbol]["fills_loaded"] = 0
            by_symbol[symbol]["error"] = str(exc)

    all_closed.sort(key=lambda t: t.closed_at)
    summary = _metrics(all_closed)
    recent_trades = [
        {
            "symbol": t.symbol,
            "side": t.side,
            "opened_at": t.opened_at,
            "closed_at": t.closed_at,
            "duration_sec": round(t.duration_sec, 1),
            "realized_pnl": round(t.realized_pnl, 8),
            "commission": round(t.commission, 8),
            "net_pnl": round(t.net_pnl, 8),
            "result": "WIN" if t.net_pnl > EPS else "LOSS" if t.net_pnl < -EPS else "BREAKEVEN",
        }
        for t in all_closed[-max(1, min(int(recent), 100)):][::-1]
    ]

    return {
        "mode": "BINANCE_DEMO",
        "scope": "ACCOUNT_USDM_TRADES_FOR_BOT_SYMBOLS",
        "note": "Статистика реконструируется из Binance Futures userTrades. Если на DEMO-аккаунте по этим парам были ручные сделки, они тоже попадут в отчёт.",
        "symbols": list(bot.SYMBOLS),
        "summary": summary,
        "by_symbol": by_symbol,
        "open_cycles": open_cycles,
        "recent_trades": recent_trades,
        "errors": errors,
    }


def _inject_live_pnl_widget() -> None:
    """Inject the display-only LIVE PnL widget without touching trade execution logic."""
    import sys

    main_module = sys.modules.get(f"{__package__}.main")
    if main_module is None or not hasattr(main_module, "PANEL_HTML"):
        return
    html = getattr(main_module, "PANEL_HTML")
    if "livePnlCard" not in html:
        setattr(main_module, "PANEL_HTML", html.replace("</body>", LIVE_PNL_SCRIPT + "</body>"))


_inject_live_pnl_widget()
