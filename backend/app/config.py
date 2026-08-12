from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class TradingSettings:
    mode: str = os.getenv("TRADING_MODE", "DEMO").strip().upper()
    demo_base_url: str = os.getenv("BINANCE_DEMO_FUTURES_URL", "https://demo-fapi.binance.com").rstrip("/")
    api_key: str = os.getenv("BINANCE_DEMO_API_KEY", "").strip()
    api_secret: str = os.getenv("BINANCE_DEMO_API_SECRET", "").strip()
    enabled: bool = _bool("ENABLE_DEMO_TRADING", False)

    leverage: int = _int("BOT_LEVERAGE", 3)
    risk_per_trade: float = _float("BOT_RISK_PER_TRADE", 0.005)
    max_daily_loss: float = _float("BOT_MAX_DAILY_LOSS", 0.02)
    max_consecutive_losses: int = _int("BOT_MAX_CONSECUTIVE_LOSSES", 3)
    min_confidence: float = _float("BOT_MIN_CONFIDENCE", 0.78)
    max_margin_fraction: float = _float("BOT_MAX_MARGIN_FRACTION", 0.25)
    recv_window: int = _int("BINANCE_RECV_WINDOW", 5000)
    allowed_symbols_raw: str = os.getenv("BOT_ALLOWED_SYMBOLS", "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT")

    @property
    def allowed_symbols(self) -> set[str]:
        return {s.strip().upper() for s in self.allowed_symbols_raw.split(",") if s.strip()}

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.mode != "DEMO":
            errors.append("TRADING_MODE должен быть DEMO. LIVE в v0.3 намеренно заблокирован.")
        if self.leverage != 3:
            errors.append("BOT_LEVERAGE должен быть 3 для текущего профиля риска.")
        if not 0 < self.risk_per_trade <= 0.01:
            errors.append("BOT_RISK_PER_TRADE должен быть > 0 и <= 0.01.")
        if not 0 < self.max_daily_loss <= 0.05:
            errors.append("BOT_MAX_DAILY_LOSS должен быть > 0 и <= 0.05.")
        if not 0.5 <= self.min_confidence <= 0.95:
            errors.append("BOT_MIN_CONFIDENCE должен быть между 0.50 и 0.95.")
        if not 0 < self.max_margin_fraction <= 0.5:
            errors.append("BOT_MAX_MARGIN_FRACTION должен быть > 0 и <= 0.5.")
        return errors


settings = TradingSettings()
