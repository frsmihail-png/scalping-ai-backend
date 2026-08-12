from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable, List, Sequence


@dataclass
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def parse_klines(rows: Sequence[Sequence]) -> List[Candle]:
    return [
        Candle(
            open_time=int(r[0]),
            open=float(r[1]),
            high=float(r[2]),
            low=float(r[3]),
            close=float(r[4]),
            volume=float(r[5]),
        )
        for r in rows
    ]


def ema(values: Sequence[float], period: int) -> List[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    out = [float(values[0])]
    for value in values[1:]:
        out.append(alpha * float(value) + (1 - alpha) * out[-1])
    return out


def sma(values: Sequence[float], period: int) -> float:
    if not values:
        return 0.0
    subset = values[-period:] if len(values) >= period else values
    return sum(subset) / len(subset)


def rsi(values: Sequence[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(values: Sequence[float]) -> tuple[float, float, float]:
    fast = ema(values, 12)
    slow = ema(values, 26)
    line = [f - s for f, s in zip(fast, slow)]
    signal_series = ema(line, 9)
    macd_line = line[-1]
    signal = signal_series[-1]
    return macd_line, signal, macd_line - signal


def true_ranges(candles: Sequence[Candle]) -> List[float]:
    if not candles:
        return []
    out = [candles[0].high - candles[0].low]
    for i in range(1, len(candles)):
        c = candles[i]
        prev_close = candles[i - 1].close
        out.append(max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close)))
    return out


def atr(candles: Sequence[Candle], period: int = 14) -> float:
    trs = true_ranges(candles)
    if len(trs) < period:
        return sma(trs, len(trs))
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
    return value


def adx(candles: Sequence[Candle], period: int = 14) -> float:
    if len(candles) <= period + 1:
        return 0.0
    trs = []
    plus_dm = []
    minus_dm = []
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]
        up = c.high - p.high
        down = p.low - c.low
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        trs.append(max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close)))

    tr_s = sum(trs[:period])
    plus_s = sum(plus_dm[:period])
    minus_s = sum(minus_dm[:period])
    dxs = []
    for i in range(period, len(trs)):
        if i > period:
            tr_s = tr_s - (tr_s / period) + trs[i]
            plus_s = plus_s - (plus_s / period) + plus_dm[i]
            minus_s = minus_s - (minus_s / period) + minus_dm[i]
        if tr_s <= 0:
            continue
        plus_di = 100 * plus_s / tr_s
        minus_di = 100 * minus_s / tr_s
        denom = plus_di + minus_di
        dxs.append(0.0 if denom == 0 else 100 * abs(plus_di - minus_di) / denom)
    if not dxs:
        return 0.0
    if len(dxs) <= period:
        return sum(dxs) / len(dxs)
    value = sum(dxs[:period]) / period
    for dx in dxs[period:]:
        value = (value * (period - 1) + dx) / period
    return value


def bollinger(values: Sequence[float], period: int = 20, mult: float = 2.0) -> tuple[float, float, float]:
    subset = list(values[-period:])
    mid = sum(subset) / len(subset)
    variance = sum((x - mid) ** 2 for x in subset) / len(subset)
    std = sqrt(variance)
    return mid - mult * std, mid, mid + mult * std


def vwap(candles: Sequence[Candle], period: int = 50) -> float:
    subset = candles[-period:]
    pv = 0.0
    vol = 0.0
    for c in subset:
        typical = (c.high + c.low + c.close) / 3
        pv += typical * c.volume
        vol += c.volume
    return pv / vol if vol else subset[-1].close


def volume_ratio(candles: Sequence[Candle], period: int = 20) -> float:
    if len(candles) < 2:
        return 1.0
    baseline = [c.volume for c in candles[-period - 1:-1]]
    avg = sum(baseline) / len(baseline) if baseline else candles[-1].volume
    return candles[-1].volume / avg if avg else 1.0


def support_resistance(candles: Sequence[Candle], lookback: int = 80) -> tuple[float, float]:
    subset = list(candles[-lookback:])
    price = subset[-1].close
    swing_lows: List[float] = []
    swing_highs: List[float] = []
    for i in range(2, len(subset) - 2):
        c = subset[i]
        if c.low <= min(x.low for x in subset[i - 2:i + 3]):
            swing_lows.append(c.low)
        if c.high >= max(x.high for x in subset[i - 2:i + 3]):
            swing_highs.append(c.high)
    below = [x for x in swing_lows if x < price]
    above = [x for x in swing_highs if x > price]
    support = max(below) if below else min(c.low for c in subset)
    resistance = min(above) if above else max(c.high for c in subset)
    return support, resistance
