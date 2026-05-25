import pytest

from quant_tool.polymarket.config import PolymarketConfig, RiskLimits


def test_risk_defaults_valid():
    limits = RiskLimits()
    assert limits.bankroll == 10_000
    assert limits.max_position_per_market == 0.02


@pytest.mark.parametrize("kwargs,msg", [
    ({"bankroll": 0}, "bankroll"),
    ({"max_position_per_market": 0}, "max_position_per_market"),
    ({"max_position_per_market": 1.5}, "max_position_per_market"),
    ({"max_position_per_market": 0.9, "max_total_exposure": 0.5}, "cannot exceed"),
])
def test_risk_validation(kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        RiskLimits(**kwargs)


def test_polymarket_config_unknown_mode_rejected():
    with pytest.raises(ValueError, match="mode"):
        PolymarketConfig(mode="dryrun")


def test_polymarket_config_strategies_must_be_non_empty():
    with pytest.raises(ValueError, match="at least one strategy"):
        PolymarketConfig(strategies=())
