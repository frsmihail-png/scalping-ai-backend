from __future__ import annotations

from dataclasses import dataclass


class RiskRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class PositionPlan:
    risk_usdt: float
    stop_distance_pct: float
    notional_usdt: float
    margin_usdt: float


def build_position_plan(
    available_balance: float,
    entry: float,
    stop_loss: float,
    leverage: int,
    risk_fraction: float,
    max_margin_fraction: float,
) -> PositionPlan:
    if available_balance <= 0 or entry <= 0:
        raise RiskRejected("Недостаточный баланс или некорректная цена")
    stop_distance = abs(entry - stop_loss)
    if stop_distance <= 0:
        raise RiskRejected("Стоп-лосс совпадает с ценой входа")

    stop_pct = stop_distance / entry
    if stop_pct < 0.0015:
        raise RiskRejected("Стоп слишком близко (<0.15%): комиссия/шум могут уничтожить преимущество")
    if stop_pct > 0.03:
        raise RiskRejected("Стоп слишком далеко (>3%): сделка не соответствует скальпинг-профилю")

    risk_usdt = available_balance * risk_fraction
    by_risk = risk_usdt / stop_pct
    max_margin = available_balance * max_margin_fraction
    max_notional = max_margin * leverage
    notional = min(by_risk, max_notional)
    margin = notional / leverage

    if notional <= 0 or margin <= 0:
        raise RiskRejected("Не удалось рассчитать безопасный размер позиции")

    return PositionPlan(
        risk_usdt=round(risk_usdt, 4),
        stop_distance_pct=round(stop_pct * 100, 4),
        notional_usdt=round(notional, 4),
        margin_usdt=round(margin, 4),
    )
