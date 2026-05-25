from datetime import datetime, timezone

from quant_tool.polymarket.data.models import (
    Market, Orderbook, OrderbookLevel, Token,
)
from quant_tool.polymarket.strategy.base import MarketSnapshot, Side
from quant_tool.polymarket.strategy.mean_reversion import MeanReversion


NOW = datetime(2026, 5, 25, tzinfo=timezone.utc)


def _market():
    return Market(
        condition_id="c1", question="q",
        tokens=(Token(token_id="yes", outcome="Yes"),
                Token(token_id="no", outcome="No")),
        tick_size=0.01, min_order_size=5.0, end_date=None, closed=False, active=True,
    )


def _snap(yes_bid, yes_ask, no_bid=0.50, no_ask=0.50):
    return MarketSnapshot(
        market=_market(),
        yes_book=Orderbook(token_id="yes",
                            bids=(OrderbookLevel(price=yes_bid, size=100),),
                            asks=(OrderbookLevel(price=yes_ask, size=100),),
                            timestamp=NOW),
        no_book=Orderbook(token_id="no",
                           bids=(OrderbookLevel(price=no_bid, size=100),),
                           asks=(OrderbookLevel(price=no_ask, size=100),),
                           timestamp=NOW),
    )


def test_silent_before_enough_history():
    mr = MeanReversion(lookback_cycles=3)
    # Feed three snapshots; need 4 to compute a 3-back move
    for _ in range(3):
        assert mr.on_snapshot(_snap(0.50, 0.52)) == ()


def test_silent_when_move_below_threshold():
    mr = MeanReversion(lookback_cycles=2, move_threshold=0.05)
    mr.on_snapshot(_snap(0.50, 0.52))  # mid 0.51
    mr.on_snapshot(_snap(0.50, 0.52))  # mid 0.51
    intents = mr.on_snapshot(_snap(0.51, 0.53))  # mid 0.52, move 0.01 < 0.05
    assert intents == ()


def test_sells_after_upward_overreaction():
    mr = MeanReversion(lookback_cycles=2, move_threshold=0.03)
    mr.on_snapshot(_snap(0.40, 0.42))  # mid 0.41
    mr.on_snapshot(_snap(0.40, 0.42))  # mid 0.41
    intents = mr.on_snapshot(_snap(0.49, 0.51))  # mid 0.50, move +0.09
    yes_intents = [i for i in intents if i.token_id == "yes"]
    assert len(yes_intents) == 1
    assert yes_intents[0].side is Side.SELL
    assert yes_intents[0].post_only is False
    assert yes_intents[0].price == 0.49  # taking at best bid


def test_buys_after_downward_overreaction():
    mr = MeanReversion(lookback_cycles=2, move_threshold=0.03)
    mr.on_snapshot(_snap(0.50, 0.52))  # mid 0.51
    mr.on_snapshot(_snap(0.50, 0.52))  # mid 0.51
    intents = mr.on_snapshot(_snap(0.40, 0.42))  # mid 0.41, move -0.10
    yes_intents = [i for i in intents if i.token_id == "yes"]
    assert len(yes_intents) == 1
    assert yes_intents[0].side is Side.BUY
    assert yes_intents[0].price == 0.42  # lifting best ask


def test_skips_extreme_price_markets():
    mr = MeanReversion(lookback_cycles=2, move_threshold=0.03,
                        min_price=0.10, max_price=0.90)
    for _ in range(3):
        # mid 0.05 -- below min_price, history should not even accumulate
        intents = mr.on_snapshot(_snap(0.04, 0.06))
    assert intents == ()
