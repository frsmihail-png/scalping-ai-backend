import importlib.abc
import importlib.machinery
import os
import sys

# Micro-scalp DEMO profile.
# We no longer use 50% of the account. The desired position is capped at
# 500 USDT notional, but it is reduced automatically when the configured stop
# plus estimated round-trip trading costs would risk more than 0.35 USDT.
os.environ["BOT_TARGET_NET_PROFIT_USDT"] = "0.10"
os.environ["BOT_PROFIT_SAFETY_BUFFER_USDT"] = "0.05"
os.environ["BOT_MAX_DAILY_LOSS"] = "0.005"
os.environ["BOT_FIXED_NOTIONAL_USDT"] = "500"
os.environ["BOT_MAX_PLANNED_LOSS_USDT"] = "0.35"


def _patch_sizing(module):
    """Install dynamic sizing without changing the exchange execution path.

    execute_signal() already calculates quantity from RISK_PER_TRADE and
    MAX_MARGIN_FRACTION. Immediately before that calculation we derive both
    values from the current available balance and the actual strategy stop.
    This makes the resulting notional approximately:

        min(500 USDT, 0.35 / (stop_pct + estimated_roundtrip_cost_rate))

    Thus a larger/looser stop automatically produces a smaller position.
    """
    if getattr(module, "_micro_scalp_sizing_v6", False):
        return

    original_balance = module._balance
    original_normalized_stop = module._normalized_stop_pct

    async def balance_with_sizing_snapshot():
        result = await original_balance()
        module._latest_sizing_balance = dict(result)
        return result

    def normalized_stop_with_dynamic_sizing(signal_entry, strategy_stop):
        stop_pct, expanded = original_normalized_stop(signal_entry, strategy_stop)
        bal = getattr(module, "_latest_sizing_balance", None) or {}
        available = float(bal.get("available_balance", 0.0) or 0.0)
        if available <= 0:
            return stop_pct, expanded

        desired_notional = float(os.getenv("BOT_FIXED_NOTIONAL_USDT", "500"))
        max_planned_loss = float(os.getenv("BOT_MAX_PLANNED_LOSS_USDT", "0.35"))
        cost_rate = (2.0 * float(module.TAKER_FEE_RATE)) + float(module.ROUNDTRIP_SLIPPAGE_RATE)

        # Planned loss includes adverse price movement to SL plus the same
        # conservative round-trip cost assumption used by the TP calculation.
        loss_capped_notional = max_planned_loss / max(stop_pct + cost_rate, 1e-9)
        selected_notional = max(0.0, min(desired_notional, loss_capped_notional))

        # Feed the selected notional into the existing dual-cap sizing formula.
        price_risk_usdt = selected_notional * stop_pct
        module.RISK_PER_TRADE = price_risk_usdt / available
        module.MAX_MARGIN_FRACTION = selected_notional / max(available * module.LEVERAGE, 1e-9)
        module._micro_scalp_sizing = {
            "desired_notional_usdt": round(desired_notional, 6),
            "selected_notional_usdt": round(selected_notional, 6),
            "max_planned_loss_usdt": round(max_planned_loss, 6),
            "stop_pct": stop_pct,
            "estimated_roundtrip_cost_rate": cost_rate,
            "estimated_loss_at_stop_usdt": round(selected_notional * (stop_pct + cost_rate), 6),
            "available_balance_usdt": round(available, 6),
        }
        return stop_pct, expanded

    module._balance = balance_with_sizing_snapshot
    module._normalized_stop_pct = normalized_stop_with_dynamic_sizing
    module._micro_scalp_sizing_v6 = True


class _SizingPatchLoader(importlib.abc.Loader):
    def __init__(self, original_loader):
        self.original_loader = original_loader

    def create_module(self, spec):
        create = getattr(self.original_loader, "create_module", None)
        return create(spec) if create else None

    def exec_module(self, module):
        self.original_loader.exec_module(module)
        _patch_sizing(module)


class _SizingPatchFinder(importlib.abc.MetaPathFinder):
    TARGET = __name__ + ".auto_demo_bot_v2"

    def find_spec(self, fullname, path=None, target=None):
        if fullname != self.TARGET:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec and spec.loader and not isinstance(spec.loader, _SizingPatchLoader):
            spec.loader = _SizingPatchLoader(spec.loader)
        return spec


# backend.app.__init__ executes before backend.app.main imports the bot module,
# so the one-shot import wrapper patches sizing before AUTO can start.
if not any(isinstance(x, _SizingPatchFinder) for x in sys.meta_path):
    sys.meta_path.insert(0, _SizingPatchFinder())
