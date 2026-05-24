from datetime import datetime, timezone

from quant_tool.polymarket.config import RiskLimits
from quant_tool.polymarket.risk.gate import RiskDecision, RiskGate
from quant_tool.polymarket.strategy.base import Intent, Side


def _intent(price=0.5, size=100.0, side=Side.BUY) -> Intent:
    return Intent(strategy="s", token_id="tok-1", side=side, price=price, size=size)


def test_approves_when_within_caps():
    gate = RiskGate(limits=RiskLimits(bankroll=10_000), starting_equity=10_000)
    assert gate.evaluate(_intent(size=100), "cond-1") is RiskDecision.APPROVED  # $50 < 2% * 10k


def test_blocks_per_market_cap():
    gate = RiskGate(limits=RiskLimits(bankroll=10_000), starting_equity=10_000)
    # 2% of 10k = $200; a $250 intent should be blocked.
    assert gate.evaluate(_intent(price=0.5, size=500), "cond-1") is RiskDecision.BLOCKED_PER_MARKET


def test_blocks_total_cap():
    limits = RiskLimits(bankroll=10_000, max_position_per_market=0.5, max_total_exposure=0.5)
    gate = RiskGate(limits=limits, starting_equity=10_000)
    gate.record_fill("cond-1", Side.BUY, 4_500)
    # New $600 BUY in cond-2 would push total above 50% * 10k = $5000.
    intent = Intent(strategy="s", token_id="tok-2", side=Side.BUY, price=0.5, size=1200)
    assert gate.evaluate(intent, "cond-2") is RiskDecision.BLOCKED_TOTAL


def test_daily_loss_kill_blocks_for_rest_of_day():
    gate = RiskGate(limits=RiskLimits(bankroll=10_000, daily_loss_kill=0.05), starting_equity=10_000)
    now = datetime(2026, 5, 24, 12, tzinfo=timezone.utc)
    gate.update_equity(9_400, now=now)  # 6% drawdown
    assert gate.evaluate(_intent(), "cond-1", now=now) is RiskDecision.BLOCKED_DAILY_LOSS


def test_bad_price_rejected():
    gate = RiskGate(limits=RiskLimits(), starting_equity=10_000)
    # Intent itself validates price in (0,1); use a price right at the bound via a different path.
    import pytest
    with pytest.raises(ValueError):
        _intent(price=0.0)
