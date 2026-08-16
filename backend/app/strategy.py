from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from .indicators import Candle, adx, atr, bollinger, ema, macd, rsi, support_resistance, volume_ratio, vwap


@dataclass
class FrameAnalysis:
    interval: str
    price: float
    ema9: float
    ema21: float
    ema50: float
    ema200: float
    rsi: float
    macd: float
    macd_signal: float
    macd_hist: float
    adx: float
    atr: float
    bb_low: float
    bb_mid: float
    bb_high: float
    vwap: float
    volume_ratio: float
    support: float
    resistance: float
    state: str
    long_score: float
    short_score: float


def analyze_frame(candles: Sequence[Candle], interval: str) -> FrameAnalysis:
    closes = [c.close for c in candles]
    price = closes[-1]
    e9 = ema(closes, 9)[-1]
    e21 = ema(closes, 21)[-1]
    e50 = ema(closes, 50)[-1]
    e200 = ema(closes, 200)[-1]
    rv = rsi(closes, 14)
    m, ms, mh = macd(closes)
    av = atr(candles, 14)
    ax = adx(candles, 14)
    bbl, bbm, bbh = bollinger(closes, 20, 2.0)
    vw = vwap(candles, 50)
    vr = volume_ratio(candles, 20)
    support, resistance = support_resistance(candles, 80)

    if e9 > e21 > e50 and price > e200:
        state = "UPTREND"
    elif e9 < e21 < e50 and price < e200:
        state = "DOWNTREND"
    elif ax < 18:
        state = "RANGE"
    else:
        state = "MIXED"

    long_score = 0.0
    short_score = 0.0

    if e9 > e21:
        long_score += 10
    else:
        short_score += 10
    if e21 > e50:
        long_score += 9
    else:
        short_score += 9
    if price > e200:
        long_score += 7
    else:
        short_score += 7

    if mh > 0:
        long_score += 8
    else:
        short_score += 8
    if 52 <= rv <= 72:
        long_score += 7
    elif 28 <= rv <= 48:
        short_score += 7
    elif rv < 25:
        long_score += 4
        short_score -= 5
    elif rv > 75:
        short_score += 4
        long_score -= 5

    if price > vw:
        long_score += 6
    else:
        short_score += 6

    if price <= bbl:
        long_score += 4
        short_score -= 3
    elif price >= bbh:
        short_score += 4
        long_score -= 3

    if ax >= 25:
        if state == "UPTREND":
            long_score += 8
        elif state == "DOWNTREND":
            short_score += 8
    elif ax < 18:
        long_score -= 2
        short_score -= 2

    if vr >= 1.35:
        if candles[-1].close >= candles[-1].open:
            long_score += 5
        else:
            short_score += 5

    distance_support = max(price - support, 0.0)
    distance_resistance = max(resistance - price, 0.0)
    if av > 0:
        if distance_support < 0.6 * av:
            short_score -= 8
            long_score += 2
        if distance_resistance < 0.6 * av:
            long_score -= 8
            short_score += 2

    return FrameAnalysis(
        interval=interval,
        price=price,
        ema9=e9,
        ema21=e21,
        ema50=e50,
        ema200=e200,
        rsi=rv,
        macd=m,
        macd_signal=ms,
        macd_hist=mh,
        adx=ax,
        atr=av,
        bb_low=bbl,
        bb_mid=bbm,
        bb_high=bbh,
        vwap=vw,
        volume_ratio=vr,
        support=support,
        resistance=resistance,
        state=state,
        long_score=max(long_score, 0.0),
        short_score=max(short_score, 0.0),
    )


def _frame_bias(frame: FrameAnalysis | None) -> str:
    if frame is None:
        return "NEUTRAL"
    diff = frame.long_score - frame.short_score
    if frame.state == "UPTREND" or diff >= 8:
        return "LONG"
    if frame.state == "DOWNTREND" or diff <= -8:
        return "SHORT"
    return "NEUTRAL"


def combine(frames: Dict[str, FrameAnalysis], primary: str = "1m") -> dict:
    # Scalping entries remain driven by short frames, but 1h/4h now act as a
    # directional regime filter so the bot does not blindly scalp against the larger move.
    weights = {"1m": 0.25, "3m": 0.20, "5m": 0.15, "15m": 0.15, "1h": 0.15, "4h": 0.10}
    active_weight = sum(weights.get(k, 0.0) for k in frames) or 1.0
    long_total = sum(frames[k].long_score * weights.get(k, 0.0) for k in frames) / active_weight
    short_total = sum(frames[k].short_score * weights.get(k, 0.0) for k in frames) / active_weight
    p = frames[primary]

    bullish = sum(1 for f in frames.values() if f.long_score > f.short_score)
    bearish = sum(1 for f in frames.values() if f.short_score > f.long_score)
    agreement_needed = max(3, (len(frames) + 1) // 2)
    if bullish >= agreement_needed:
        long_total += 8
    if bearish >= agreement_needed:
        short_total += 8

    h1_bias = _frame_bias(frames.get("1h"))
    h4_bias = _frame_bias(frames.get("4h"))
    higher_tf_bias = "NEUTRAL"
    if h1_bias == h4_bias and h1_bias in {"LONG", "SHORT"}:
        higher_tf_bias = h1_bias
    elif h1_bias in {"LONG", "SHORT"} and h4_bias == "NEUTRAL":
        higher_tf_bias = h1_bias
    elif h4_bias in {"LONG", "SHORT"} and h1_bias == "NEUTRAL":
        higher_tf_bias = h4_bias
    elif h1_bias != h4_bias and h1_bias != "NEUTRAL" and h4_bias != "NEUTRAL":
        higher_tf_bias = "CONFLICT"

    dominant = max(long_total, short_total)
    diff = abs(long_total - short_total)
    raw_conf = min(0.95, max(0.50, dominant / 75.0))

    candidate = "HOLD"
    if diff >= 9 and raw_conf >= 0.68:
        candidate = "BUY" if long_total > short_total else "SELL"

    warnings: List[str] = []
    reasons: List[str] = []

    # Hard regime protection: do not open directly against a confirmed 1h+4h trend.
    action = candidate
    if candidate == "BUY" and higher_tf_bias == "SHORT":
        action = "HOLD"
        raw_conf = min(raw_conf, 0.76)
        warnings.append("BUY заблокирован: 1h/4h подтверждают нисходящее направление")
    elif candidate == "SELL" and higher_tf_bias == "LONG":
        action = "HOLD"
        raw_conf = min(raw_conf, 0.76)
        warnings.append("SELL заблокирован: 1h/4h подтверждают восходящее направление")
    elif higher_tf_bias == "CONFLICT":
        action = "HOLD"
        raw_conf = min(raw_conf, 0.72)
        warnings.append("1h и 4h конфликтуют — вход отложен до согласования направления")

    if p.ema9 > p.ema21:
        reasons.append("EMA9 выше EMA21: краткосрочный импульс бычий")
    else:
        reasons.append("EMA9 ниже EMA21: краткосрочный импульс медвежий")
    reasons.append(f"RSI {p.rsi:.1f}")
    reasons.append(f"ADX {p.adx:.1f}: " + ("тренд выраженный" if p.adx >= 25 else "сила тренда умеренная/низкая"))
    reasons.append("Цена выше VWAP" if p.price > p.vwap else "Цена ниже VWAP")
    if p.volume_ratio >= 1.35:
        reasons.append(f"Объём повышен: {p.volume_ratio:.2f}× среднего")
    if bullish >= agreement_needed:
        reasons.append(f"{bullish}/{len(frames)} таймфреймов склоняются в LONG")
    elif bearish >= agreement_needed:
        reasons.append(f"{bearish}/{len(frames)} таймфреймов склоняются в SHORT")
    else:
        reasons.append("Таймфреймы не дают согласованного направления")
    if "1h" in frames or "4h" in frames:
        reasons.append(f"Старший тренд: 1h={h1_bias}, 4h={h4_bias}")

    if p.rsi < 25 and p.state == "DOWNTREND":
        warnings.append("RSI в глубокой перепроданности: новый SHORT может быть запоздалым")
    if p.rsi > 75 and p.state == "UPTREND":
        warnings.append("RSI в перекупленности: новый LONG может быть запоздалым")

    entry = p.price
    stop_loss = take1 = take2 = take3 = rr = None
    if action == "BUY":
        risk = max(p.atr * 1.15, entry - p.support if p.support < entry else 0.0)
        risk = max(risk, p.atr * 0.8)
        stop_loss = entry - risk
        take1 = entry + risk * 1.2
        take2 = entry + risk * 2.0
        take3 = entry + risk * 3.0
        rr = 2.0
    elif action == "SELL":
        risk = max(p.atr * 1.15, p.resistance - entry if p.resistance > entry else 0.0)
        risk = max(risk, p.atr * 0.8)
        stop_loss = entry + risk
        take1 = entry - risk * 1.2
        take2 = entry - risk * 2.0
        take3 = entry - risk * 3.0
        rr = 2.0
    else:
        raw_conf = min(raw_conf, 0.76)
        if not warnings:
            warnings.append("Нет достаточного преимущества BUY или SELL — лучше ждать подтверждения")

    decimals = 4 if entry < 10 else 2
    q = lambda x: None if x is None else round(x, decimals)

    return {
        "action": action,
        "candidate_action": candidate,
        "confidence": round(raw_conf, 4),
        "price": q(p.price),
        "entry": q(entry),
        "support": q(p.support),
        "resistance": q(p.resistance),
        "market_state": p.state,
        "higher_timeframe_bias": higher_tf_bias,
        "stop_loss": q(stop_loss),
        "take_profit": q(take1),
        "take_profit_2": q(take2),
        "take_profit_3": q(take3),
        "risk_reward": rr,
        "reasons": reasons,
        "warnings": warnings,
        "indicators": {
            "ema9": round(p.ema9, decimals),
            "ema21": round(p.ema21, decimals),
            "ema50": round(p.ema50, decimals),
            "ema200": round(p.ema200, decimals),
            "rsi": round(p.rsi, 2),
            "macd": round(p.macd, 6),
            "macd_signal": round(p.macd_signal, 6),
            "macd_hist": round(p.macd_hist, 6),
            "adx": round(p.adx, 2),
            "atr": round(p.atr, decimals),
            "vwap": round(p.vwap, decimals),
            "volume_ratio": round(p.volume_ratio, 2),
            "long_score": round(long_total, 2),
            "short_score": round(short_total, 2),
            "ml_samples": 0.0,
        },
        "timeframes": {
            k: {
                "state": f.state,
                "rsi": round(f.rsi, 2),
                "adx": round(f.adx, 2),
                "long_score": round(f.long_score, 2),
                "short_score": round(f.short_score, 2),
                "bias": _frame_bias(f),
            }
            for k, f in frames.items()
        },
    }
