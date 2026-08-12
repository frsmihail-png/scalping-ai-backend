import pytest

from app.risk import RiskRejected, build_position_plan


def test_position_plan_caps_margin():
    plan = build_position_plan(
        available_balance=1000,
        entry=100,
        stop_loss=99,
        leverage=3,
        risk_fraction=0.005,
        max_margin_fraction=0.25,
    )
    assert plan.risk_usdt == 5.0
    assert plan.margin_usdt <= 250
    assert plan.notional_usdt <= 750


def test_rejects_too_tight_stop():
    with pytest.raises(RiskRejected):
        build_position_plan(1000, 100, 99.9, 3, 0.005, 0.25)


def test_rejects_too_wide_stop():
    with pytest.raises(RiskRejected):
        build_position_plan(1000, 100, 95, 3, 0.005, 0.25)
