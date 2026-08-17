import os

# Canonical DEMO sizing profile.
# With 3x leverage, MAX_MARGIN_FRACTION=0.50 means each new position may use
# approximately 50% of the currently available USDT as isolated margin.
# RISK_PER_TRADE is deliberately set above the worst allowed stop distance so
# execute_signal() is capped by MAX_MARGIN_FRACTION rather than the legacy
# risk-based notional calculation. The actual quantity is still rounded to the
# exchange MARKET_LOT_SIZE / LOT_SIZE rules.
os.environ["BOT_MAX_MARGIN_FRACTION"] = "0.50"
os.environ["BOT_RISK_PER_TRADE"] = "0.02"

# Keep the requested scalping objective explicit at process start. main.py also
# pins these values so stale Render environment variables cannot override them.
os.environ["BOT_TARGET_NET_PROFIT_USDT"] = "0.10"
os.environ["BOT_PROFIT_SAFETY_BUFFER_USDT"] = "0.05"
