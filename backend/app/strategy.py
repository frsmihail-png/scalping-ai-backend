from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from .indicators import (
    Candle, adx, atr, bb_width, bollinger, candle_pattern, cci, cmf, di_values,
    ema, ichimoku, keltner, macd, mfi, obv, roc, rsi, stochastic, stoch_rsi,
    supertrend, support_resistance, volume_ratio, vwap, williams_r,
)


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
    plus_di: float
    minus_di: float
    atr: float
    bb_low: float
    bb_mid: float
    bb_high: float
    bb_width: float
    vwap: float
    volume_ratio: float
    support: float
    resistance: float
    stoch_k: float
    stoch_d: float
    stoch_rsi: float
    cci: float
    roc: float
    williams_r: float
    obv_slope: float
    mfi: float
    cmf: float
    kc_low: float
    kc_mid: float
    kc_high: float
    supertrend_bias: str
    ichimoku_bias: str
    candle_pattern: str
    state: str
    long_score: float
    short_score: float


def analyze_frame(candles: Sequence[Candle], interval: str) -> FrameAnalysis:
    closes = [c.close for c in candles]
    price = closes[-1]
    e9, e21, e50, e200 = ema(closes, 9)[-1], ema(closes, 21)[-1], ema(closes, 50)[-1], ema(closes, 200)[-1]
    rv = rsi(closes, 14)
    m, ms, mh = macd(closes)
    av = atr(candles, 14)
    ax = adx(candles, 14)
    pdi, mdi = di_values(candles, 14)
    bbl, bbm, bbh = bollinger(closes, 20, 2.0)
    bbw = bb_width(closes, 20, 2.0)
    vw = vwap(candles, 50)
    vr = volume_ratio(candles, 20)
    support, resistance = support_resistance(candles, 80)
    sk, sd = stochastic(candles, 14)
    srsi = stoch_rsi(closes, 14)
    cc = cci(candles, 20)
    rc = roc(closes, 12)
    wr = williams_r(candles, 14)
    _, obv_slope = obv(candles)
    mf = mfi(candles, 14)
    cf = cmf(candles, 20)
    kcl, kcm, kch = keltner(candles, 20, 1.5)
    _, st_bias = supertrend(candles, 10, 3.0)
    _, _, _, _, ichi_bias = ichimoku(candles)
    pattern = candle_pattern(candles)

    if e9 > e21 > e50 and price > e200 and pdi > mdi:
        state = "UPTREND"
    elif e9 < e21 < e50 and price < e200 and mdi > pdi:
        state = "DOWNTREND"
    elif ax < 18 and bbw < 0.03:
        state = "RANGE"
    elif vr >= 1.5 and bbw >= 0.03:
        state = "BREAKOUT"
    else:
        state = "MIXED"

    long_score = 0.0
    short_score = 0.0

    # Trend block: dominant block. Trend signals receive more weight than
    # oscillators so the bot does not constantly fade a strong move.
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
    if st_bias == "LONG":
        long_score += 9
    elif st_bias == "SHORT":
        short_score += 9
    if ichi_bias == "LONG":
        long_score += 8
    elif ichi_bias == "SHORT":
        short_score += 8
    if ax >= 22:
        if pdi > mdi:
            long_score += 8
        elif mdi > pdi:
            short_score += 8

    # Momentum block. In a trend, momentum must confirm the direction.
    if mh > 0:
        long_score += 7
    elif mh < 0:
        short_score += 7
    if rc > 0:
        long_score += 4
    elif rc < 0:
        short_score += 4
    if 52 <= rv <= 72:
        long_score += 5
    elif 28 <= rv <= 48:
        short_score += 5
    if sk > sd and sk < 90:
        long_score += 4
    elif sk < sd and sk > 10:
        short_score += 4
    if cc > 50:
        long_score += 3
    elif cc < -50:
        short_score += 3

    # Mean-reversion oscillators are only allowed to matter in RANGE/MIXED.
    # Previously they could fight a strong trend and create wrong-way entries.
    if state in {"RANGE", "MIXED"} and ax < 24:
        if srsi < 15:
            long_score += 2
        elif srsi > 85:
            short_score += 2
        if wr < -85:
            long_score += 2
        elif wr > -15:
            short_score += 2

    # Volume / money-flow block.
    if price > vw:
        long_score += 6
    else:
        short_score += 6
    if obv_slope > 0:
        long_score += 5
    elif obv_slope < 0:
        short_score += 5
    if mf > 55:
        long_score += 4
    elif mf < 45:
        short_score += 4
    if cf > 0.05:
        long_score += 5
    elif cf < -0.05:
        short_score += 5
    if vr >= 1.35:
        if candles[-1].close >= candles[-1].open:
            long_score += 5
        else:
            short_score += 5

    # Volatility / location. Mean reversion at Bollinger/Keltner extremes is
    # only useful in range-like markets. In trends an outer-band touch can be
    # continuation, so do not automatically trade against it.
    if state in {"RANGE", "MIXED"} and ax < 24:
        if price <= bbl or price <= kcl:
            long_score += 3
            short_score -= 2
        elif price >= bbh or price >= kch:
            short_score += 3
            long_score -= 2
    elif state in {"UPTREND", "BREAKOUT"} and price >= bbm:
        long_score += 2
    elif state == "DOWNTREND" and price <= bbm:
        short_score += 2

    # Price action.
    if pattern in {"BULL_ENGULFING", "BULL_PIN", "BULL_IMPULSE"}:
        long_score += 6
    elif pattern in {"BEAR_ENGULFING", "BEAR_PIN", "BEAR_IMPULSE"}:
        short_score += 6

    distance_support = max(price - support, 0.0)
    distance_resistance = max(resistance - price, 0.0)
    if av > 0:
        if distance_support < 0.6 * av:
            short_score -= 12
            long_score += 2
        if distance_resistance < 0.6 * av:
            long_score -= 12
            short_score += 2

    return FrameAnalysis(
        interval, price, e9, e21, e50, e200, rv, m, ms, mh, ax, pdi, mdi, av,
        bbl, bbm, bbh, bbw, vw, vr, support, resistance, sk, sd, srsi, cc, rc,
        wr, obv_slope, mf, cf, kcl, kcm, kch, st_bias, ichi_bias, pattern,
        state, max(long_score, 0.0), max(short_score, 0.0),
    )


def _frame_bias(frame: FrameAnalysis | None) -> str:
    if frame is None:
        return "NEUTRAL"
    diff = frame.long_score - frame.short_score
    if frame.state == "UPTREND" or diff >= 12:
        return "LONG"
    if frame.state == "DOWNTREND" or diff <= -12:
        return "SHORT"
    return "NEUTRAL"


def combine(frames: Dict[str, FrameAnalysis], primary: str = "1m") -> dict:
    weights = {"1m": 0.18, "3m": 0.16, "5m": 0.16, "15m": 0.16, "1h": 0.18, "4h": 0.16}
    active_weight = sum(weights.get(k, 0.0) for k in frames) or 1.0
    long_total = sum(frames[k].long_score * weights.get(k, 0.0) for k in frames) / active_weight
    short_total = sum(frames[k].short_score * weights.get(k, 0.0) for k in frames) / active_weight
    p = frames[primary]

    bullish = sum(1 for f in frames.values() if f.long_score > f.short_score)
    bearish = sum(1 for f in frames.values() if f.short_score > f.long_score)
    agreement_needed = 4 if len(frames) >= 6 else max(3, (len(frames) + 1) // 2)
    if bullish >= agreement_needed:
        long_total += 10
    if bearish >= agreement_needed:
        short_total += 10

    h1_bias, h4_bias = _frame_bias(frames.get("1h")), _frame_bias(frames.get("4h"))
    if h1_bias == h4_bias and h1_bias in {"LONG", "SHORT"}:
        higher_tf_bias = h1_bias
    elif h1_bias in {"LONG", "SHORT"} and h4_bias == "NEUTRAL":
        higher_tf_bias = h1_bias
    elif h4_bias in {"LONG", "SHORT"} and h1_bias == "NEUTRAL":
        higher_tf_bias = h4_bias
    elif h1_bias != h4_bias and h1_bias != "NEUTRAL" and h4_bias != "NEUTRAL":
        higher_tf_bias = "CONFLICT"
    else:
        higher_tf_bias = "NEUTRAL"

    dominant = max(long_total, short_total)
    diff = abs(long_total - short_total)
    raw_conf = min(0.96, max(0.50, dominant / 100.0))

    candidate = "HOLD"
    # More selective than V2.0: require a material score gap and at least 77%
    # raw confidence before a direction can become executable.
    if diff >= 18 and raw_conf >= 0.77:
        candidate = "BUY" if long_total > short_total else "SELL"

    warnings: List[str] = []
    reasons: List[str] = []
    action = candidate

    if candidate == "BUY" and higher_tf_bias == "SHORT":
        action = "HOLD"
        raw_conf = min(raw_conf, 0.76)
        warnings.append("BUY заблокирован старшим нисходящим трендом")
    elif candidate == "SELL" and higher_tf_bias == "LONG":
        action = "HOLD"
        raw_conf = min(raw_conf, 0.76)
        warnings.append("SELL заблокирован старшим восходящим трендом")
    elif higher_tf_bias == "CONFLICT":
        action = "HOLD"
        raw_conf = min(raw_conf, 0.72)
        warnings.append("1h и 4h конфликтуют")

    # If higher timeframes are neutral, require unusually strong agreement.
    if candidate in {"BUY", "SELL"} and higher_tf_bias == "NEUTRAL":
        same_side = bullish if candidate == "BUY" else bearish
        if same_side < max(5, agreement_needed):
            action = "HOLD"
            raw_conf = min(raw_conf, 0.76)
            warnings.append("Нет подтверждения 1h/4h: для входа нужно 5/6 таймфреймов")

    if p.adx < 18 and p.state == "RANGE":
        action = "HOLD"
        raw_conf = min(raw_conf, 0.74)
        warnings.append("Слабый тренд: ADX низкий, рынок во флэте")
    if candidate == "BUY" and p.rsi > 72 and p.stoch_rsi > 85:
        action = "HOLD"
        raw_conf = min(raw_conf, 0.75)
        warnings.append("LONG перегрет: RSI/StochRSI")
    if candidate == "SELL" and p.rsi < 28 and p.stoch_rsi < 15:
        action = "HOLD"
        raw_conf = min(raw_conf, 0.75)
        warnings.append("SHORT запоздал: RSI/StochRSI перепроданы")

    # Do not enter against the immediate 1m/3m impulse. This is deliberately a
    # veto, not a mirror switch: blindly reversing a losing strategy does not
    # remove fees, slippage or bad timing.
    f1 = frames.get("1m")
    f3 = frames.get("3m")
    if action == "BUY" and f1 and f3 and f1.macd_hist < 0 and f3.macd_hist < 0:
        action = "HOLD"
        raw_conf = min(raw_conf, 0.76)
        warnings.append("BUY заблокирован: импульс 1m/3m ещё вниз")
    if action == "SELL" and f1 and f3 and f1.macd_hist > 0 and f3.macd_hist > 0:
        action = "HOLD"
        raw_conf = min(raw_conf, 0.76)
        warnings.append("SELL заблокирован: импульс 1m/3m ещё вверх")

    reasons += [
        f"EMA trend: {'LONG' if p.ema9 > p.ema21 else 'SHORT'}",
        f"SuperTrend: {p.supertrend_bias}",
        f"Ichimoku: {p.ichimoku_bias}",
        f"RSI {p.rsi:.1f}, StochRSI {p.stoch_rsi:.1f}, CCI {p.cci:.1f}",
        f"ADX {p.adx:.1f}, +DI {p.plus_di:.1f}, -DI {p.minus_di:.1f}",
        f"MFI {p.mfi:.1f}, CMF {p.cmf:.3f}, Vol {p.volume_ratio:.2f}x",
        f"Pattern: {p.candle_pattern}",
        f"HTF: 1h={h1_bias}, 4h={h4_bias}",
        f"Consensus: LONG {bullish}/{len(frames)}, SHORT {bearish}/{len(frames)}",
    ]

    entry = p.price
    stop_loss = take1 = take2 = take3 = rr = None
    if action == "BUY":
        risk = max(p.atr * 1.0, entry - p.support if p.support < entry else 0.0, p.atr * 0.7)
        stop_loss = entry - risk
        take1 = entry + risk * 1.3
        take2 = entry + risk * 2.0
        take3 = entry + risk * 3.0
        rr = 1.3
    elif action == "SELL":
        risk = max(p.atr * 1.0, p.resistance - entry if p.resistance > entry else 0.0, p.atr * 0.7)
        stop_loss = entry + risk
        take1 = entry - risk * 1.3
        take2 = entry - risk * 2.0
        take3 = entry - risk * 3.0
        rr = 1.3
    else:
        raw_conf = min(raw_conf, 0.76)
        if not warnings:
            warnings.append("Недостаточно независимых подтверждений для входа")

    decimals = 4 if entry < 10 else 2
    q = lambda x: None if x is None else round(x, decimals)

    indicator_snapshot = {
        "ema9": round(p.ema9, decimals),
        "ema21": round(p.ema21, decimals),
        "ema50": round(p.ema50, decimals),
        "ema200": round(p.ema200, decimals),
        "rsi": round(p.rsi, 2),
        "macd": round(p.macd, 6),
        "macd_signal": round(p.macd_signal, 6),
        "macd_hist": round(p.macd_hist, 6),
        "adx": round(p.adx, 2),
        "plus_di": round(p.plus_di, 2),
        "minus_di": round(p.minus_di, 2),
        "atr": round(p.atr, decimals),
        "vwap": round(p.vwap, decimals),
        "bb_width": round(p.bb_width, 6),
        "volume_ratio": round(p.volume_ratio, 2),
        "stoch_k": round(p.stoch_k, 2),
        "stoch_d": round(p.stoch_d, 2),
        "stoch_rsi": round(p.stoch_rsi, 2),
        "cci": round(p.cci, 2),
        "roc": round(p.roc, 3),
        "williams_r": round(p.williams_r, 2),
        "obv_slope": round(p.obv_slope, 3),
        "mfi": round(p.mfi, 2),
        "cmf": round(p.cmf, 4),
        "supertrend_bias": p.supertrend_bias,
        "ichimoku_bias": p.ichimoku_bias,
        "candle_pattern": p.candle_pattern,
        "long_score": round(long_total, 2),
        "short_score": round(short_total, 2),
        "ml_samples": 0.0,
    }

    mirror_shadow_action = "SELL" if candidate == "BUY" else "BUY" if candidate == "SELL" else "HOLD"

    return {
        "strategy_engine": "V2.1_QUALITY_FIRST",
        "action": action,
        "candidate_action": candidate,
        "mirror_shadow_action": mirror_shadow_action,
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
        "indicators": indicator_snapshot,
        "timeframes": {
            k: {
                "state": f.state,
                "rsi": round(f.rsi, 2),
                "adx": round(f.adx, 2),
                "long_score": round(f.long_score, 2),
                "short_score": round(f.short_score, 2),
                "bias": _frame_bias(f),
                "supertrend": f.supertrend_bias,
                "ichimoku": f.ichimoku_bias,
            }
            for k, f in frames.items()
        },
        "feature_snapshot": indicator_snapshot,
    }
