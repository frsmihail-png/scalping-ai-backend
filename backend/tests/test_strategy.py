from app.indicators import Candle
from app.strategy import analyze_frame, combine


def candles(n=260, start=100.0, step=0.08):
    out=[]
    p=start
    for i in range(n):
        o=p
        c=p+step
        out.append(Candle(i, o, max(o,c)+0.1, min(o,c)-0.1, c, 100+i%10))
        p=c
    return out


def test_analysis_shape():
    frames={tf: analyze_frame(candles(), tf) for tf in ["1m","3m","5m","15m"]}
    result=combine(frames,"1m")
    assert result["action"] in {"BUY","SELL","HOLD"}
    assert 0.5 <= result["confidence"] <= 0.95
    assert result["support"] < result["price"]
    assert result["resistance"] > result["price"]
