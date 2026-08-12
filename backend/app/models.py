from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class AnalyzeRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", min_length=5, max_length=20)
    interval: str = Field(default="1m")

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper().replace("/", "")
        if not value.isalnum():
            raise ValueError("Некорректный символ")
        return value

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, value: str) -> str:
        allowed = {"1m", "3m", "5m", "15m"}
        if value not in allowed:
            raise ValueError(f"Интервал должен быть одним из: {', '.join(sorted(allowed))}")
        return value


class AnalyzeResponse(BaseModel):
    symbol: str
    action: str
    confidence: float
    price: float
    entry: float
    support: float
    resistance: float
    market_state: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_reward: Optional[float] = None
    reasons: List[str]
    warnings: List[str] = []
    indicators: Dict[str, float]
    timeframes: Dict[str, Dict[str, float | str]]
