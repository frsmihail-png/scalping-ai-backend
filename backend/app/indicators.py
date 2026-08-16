from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import List, Sequence


@dataclass
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def parse_klines(rows: Sequence[Sequence]) -> List[Candle]:
    return [Candle(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in rows]


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
    subset = list(values[-period:]) if len(values) >= period else list(values)
    return sum(subset) / len(subset)


def rsi_series(values: Sequence[float], period: int = 14) -> List[float]:
    if len(values) <= period:
        return [50.0] * len(values)
    out = [50.0] * period
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0.0)); losses.append(max(-diff, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    def calc(g: float, l: float) -> float:
        if l == 0: return 100.0
        rs = g / l
        return 100 - (100 / (1 + rs))
    out.append(calc(avg_gain, avg_loss))
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        out.append(calc(avg_gain, avg_loss))
    return out[-len(values):]


def rsi(values: Sequence[float], period: int = 14) -> float:
    return rsi_series(values, period)[-1] if values else 50.0


def macd(values: Sequence[float]) -> tuple[float, float, float]:
    fast, slow = ema(values, 12), ema(values, 26)
    line = [f - s for f, s in zip(fast, slow)]
    signal_series = ema(line, 9)
    return line[-1], signal_series[-1], line[-1] - signal_series[-1]


def true_ranges(candles: Sequence[Candle]) -> List[float]:
    if not candles: return []
    out = [candles[0].high - candles[0].low]
    for i in range(1, len(candles)):
        c, pc = candles[i], candles[i - 1].close
        out.append(max(c.high - c.low, abs(c.high - pc), abs(c.low - pc)))
    return out


def atr(candles: Sequence[Candle], period: int = 14) -> float:
    trs = true_ranges(candles)
    if not trs: return 0.0
    if len(trs) < period: return sma(trs, len(trs))
    value = sum(trs[:period]) / period
    for tr in trs[period:]: value = (value * (period - 1) + tr) / period
    return value


def di_values(candles: Sequence[Candle], period: int = 14) -> tuple[float, float]:
    if len(candles) <= period + 1: return 0.0, 0.0
    trs=[]; plus=[]; minus=[]
    for i in range(1, len(candles)):
        c,p=candles[i],candles[i-1]
        up=c.high-p.high; down=p.low-c.low
        plus.append(up if up>down and up>0 else 0.0); minus.append(down if down>up and down>0 else 0.0)
        trs.append(max(c.high-c.low, abs(c.high-p.close), abs(c.low-p.close)))
    tr_s=sum(trs[:period]); p_s=sum(plus[:period]); m_s=sum(minus[:period])
    for i in range(period, len(trs)):
        tr_s=tr_s-tr_s/period+trs[i]; p_s=p_s-p_s/period+plus[i]; m_s=m_s-m_s/period+minus[i]
    if tr_s<=0: return 0.0,0.0
    return 100*p_s/tr_s, 100*m_s/tr_s


def adx(candles: Sequence[Candle], period: int = 14) -> float:
    if len(candles) <= period + 1: return 0.0
    trs=[]; plus_dm=[]; minus_dm=[]
    for i in range(1,len(candles)):
        c,p=candles[i],candles[i-1]; up=c.high-p.high; down=p.low-c.low
        plus_dm.append(up if up>down and up>0 else 0.0); minus_dm.append(down if down>up and down>0 else 0.0)
        trs.append(max(c.high-c.low,abs(c.high-p.close),abs(c.low-p.close)))
    tr_s=sum(trs[:period]); plus_s=sum(plus_dm[:period]); minus_s=sum(minus_dm[:period]); dxs=[]
    for i in range(period,len(trs)):
        if i>period:
            tr_s=tr_s-tr_s/period+trs[i]; plus_s=plus_s-plus_s/period+plus_dm[i]; minus_s=minus_s-minus_s/period+minus_dm[i]
        if tr_s<=0: continue
        pdi=100*plus_s/tr_s; mdi=100*minus_s/tr_s; den=pdi+mdi
        dxs.append(0.0 if den==0 else 100*abs(pdi-mdi)/den)
    if not dxs: return 0.0
    value=sum(dxs[:period])/min(period,len(dxs))
    for dx in dxs[period:]: value=(value*(period-1)+dx)/period
    return value


def bollinger(values: Sequence[float], period: int = 20, mult: float = 2.0) -> tuple[float,float,float]:
    subset=list(values[-period:]); mid=sum(subset)/len(subset); var=sum((x-mid)**2 for x in subset)/len(subset); std=sqrt(var)
    return mid-mult*std, mid, mid+mult*std


def bb_width(values: Sequence[float], period: int = 20, mult: float = 2.0) -> float:
    low,mid,high=bollinger(values,period,mult)
    return (high-low)/mid if mid else 0.0


def vwap(candles: Sequence[Candle], period: int = 50) -> float:
    subset=candles[-period:]; pv=vol=0.0
    for c in subset:
        typical=(c.high+c.low+c.close)/3; pv+=typical*c.volume; vol+=c.volume
    return pv/vol if vol else subset[-1].close


def volume_ratio(candles: Sequence[Candle], period: int = 20) -> float:
    if len(candles)<2:return 1.0
    baseline=[c.volume for c in candles[-period-1:-1]]; avg=sum(baseline)/len(baseline) if baseline else candles[-1].volume
    return candles[-1].volume/avg if avg else 1.0


def support_resistance(candles: Sequence[Candle], lookback: int = 80) -> tuple[float,float]:
    subset=list(candles[-lookback:]); price=subset[-1].close; lows=[]; highs=[]
    for i in range(2,len(subset)-2):
        c=subset[i]
        if c.low<=min(x.low for x in subset[i-2:i+3]): lows.append(c.low)
        if c.high>=max(x.high for x in subset[i-2:i+3]): highs.append(c.high)
    below=[x for x in lows if x<price]; above=[x for x in highs if x>price]
    return max(below) if below else min(c.low for c in subset), min(above) if above else max(c.high for c in subset)


def stochastic(candles: Sequence[Candle], period: int = 14) -> tuple[float,float]:
    if not candles:return 50.0,50.0
    ks=[]
    for i in range(max(0,len(candles)-5),len(candles)):
        window=candles[max(0,i-period+1):i+1]; lo=min(c.low for c in window); hi=max(c.high for c in window)
        ks.append(50.0 if hi==lo else 100*(candles[i].close-lo)/(hi-lo))
    k=ks[-1]; d=sum(ks[-3:])/min(3,len(ks))
    return k,d


def stoch_rsi(values: Sequence[float], period: int = 14) -> float:
    rs=rsi_series(values,period)
    window=rs[-period:]; lo=min(window); hi=max(window)
    return 50.0 if hi==lo else 100*(rs[-1]-lo)/(hi-lo)


def cci(candles: Sequence[Candle], period: int = 20) -> float:
    subset=list(candles[-period:]); tps=[(c.high+c.low+c.close)/3 for c in subset]; mean=sum(tps)/len(tps); dev=sum(abs(x-mean) for x in tps)/len(tps)
    return 0.0 if dev==0 else (tps[-1]-mean)/(0.015*dev)


def roc(values: Sequence[float], period: int = 12) -> float:
    if len(values)<=period or values[-period-1]==0:return 0.0
    return 100*(values[-1]-values[-period-1])/values[-period-1]


def williams_r(candles: Sequence[Candle], period: int = 14) -> float:
    subset=list(candles[-period:]); hi=max(c.high for c in subset); lo=min(c.low for c in subset)
    return -50.0 if hi==lo else -100*(hi-candles[-1].close)/(hi-lo)


def obv(candles: Sequence[Candle]) -> tuple[float,float]:
    value=0.0; series=[0.0]
    for i in range(1,len(candles)):
        if candles[i].close>candles[i-1].close:value+=candles[i].volume
        elif candles[i].close<candles[i-1].close:value-=candles[i].volume
        series.append(value)
    slope=value-series[-6] if len(series)>=6 else value-series[0]
    return value,slope


def mfi(candles: Sequence[Candle], period: int = 14) -> float:
    if len(candles)<=period:return 50.0
    pos=neg=0.0
    for i in range(len(candles)-period,len(candles)):
        tp=(candles[i].high+candles[i].low+candles[i].close)/3; prev=(candles[i-1].high+candles[i-1].low+candles[i-1].close)/3; flow=tp*candles[i].volume
        if tp>=prev:pos+=flow
        else:neg+=flow
    if neg==0:return 100.0
    ratio=pos/neg; return 100-(100/(1+ratio))


def cmf(candles: Sequence[Candle], period: int = 20) -> float:
    subset=list(candles[-period:]); mfv=vol=0.0
    for c in subset:
        mult=0.0 if c.high==c.low else ((c.close-c.low)-(c.high-c.close))/(c.high-c.low)
        mfv+=mult*c.volume; vol+=c.volume
    return mfv/vol if vol else 0.0


def keltner(candles: Sequence[Candle], period: int = 20, mult: float = 1.5) -> tuple[float,float,float]:
    closes=[c.close for c in candles]; mid=ema(closes,period)[-1]; av=atr(candles,period)
    return mid-mult*av,mid,mid+mult*av


def supertrend(candles: Sequence[Candle], period: int = 10, mult: float = 3.0) -> tuple[float,str]:
    if len(candles)<period+2:return candles[-1].close,"NEUTRAL"
    av=atr(candles,period); c=candles[-1]; mid=(c.high+c.low)/2; upper=mid+mult*av; lower=mid-mult*av
    prev=candles[-2].close
    if c.close>upper or (c.close>prev and c.close>mid): return lower,"LONG"
    if c.close<lower or (c.close<prev and c.close<mid): return upper,"SHORT"
    return mid,"NEUTRAL"


def ichimoku(candles: Sequence[Candle]) -> tuple[float,float,float,float,str]:
    def mid(n:int)->float:
        s=candles[-n:]; return (max(c.high for c in s)+min(c.low for c in s))/2
    tenkan=mid(9); kijun=mid(26); span_a=(tenkan+kijun)/2; span_b=mid(52); price=candles[-1].close
    top=max(span_a,span_b); bottom=min(span_a,span_b)
    bias="LONG" if price>top and tenkan>kijun else "SHORT" if price<bottom and tenkan<kijun else "NEUTRAL"
    return tenkan,kijun,span_a,span_b,bias


def candle_pattern(candles: Sequence[Candle]) -> str:
    if len(candles)<2:return "NONE"
    p,c=candles[-2],candles[-1]; body=abs(c.close-c.open); rng=max(c.high-c.low,1e-12); upper=c.high-max(c.open,c.close); lower=min(c.open,c.close)-c.low
    if c.close>c.open and p.close<p.open and c.open<=p.close and c.close>=p.open:return "BULL_ENGULFING"
    if c.close<c.open and p.close>p.open and c.open>=p.close and c.close<=p.open:return "BEAR_ENGULFING"
    if lower>2*body and upper<body and body/rng<0.4:return "BULL_PIN"
    if upper>2*body and lower<body and body/rng<0.4:return "BEAR_PIN"
    if body/rng>0.75:return "BULL_IMPULSE" if c.close>c.open else "BEAR_IMPULSE"
    return "NONE"
