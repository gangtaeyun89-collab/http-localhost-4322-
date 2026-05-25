from datetime import datetime, timezone

from quant_tool.polymarket.data.models import (
    Market,
    Orderbook,
    OrderbookLevel,
    Token,
)
from quant_tool.polymarket.strategy.arb_yes_no import YesNoArb
from quant_tool.polymarket.strategy.base import MarketSnapshot, Side
from quant_tool.polymarket.strategy.market_maker import MarketMaker
from quant_tool.polymarket.strategy.signal_model import SignalModel


NOW = datetime(2026, 5, 24, tzinfo=timezone.utc)


def _market() -> Market:
    return Market(
        condition_id="cond-1",
        question="Will X happen?",
        tokens=(Token(token_id="yes", outcome="Yes"), Token(token_id="no", outcome="No")),
        tick_size=0.01,
        min_order_size=5.0,
        end_date=None,
        closed=False,
        active=True,
    )


def _book(token, bid, ask, bid_size=200, ask_size=200, extra_levels=()):
    bids = (OrderbookLevel(price=bid, size=bid_size),)
    asks = (OrderbookLevel(price=ask, size=ask_size),)
    for price, size, side in extra_levels:
        level = OrderbookLevel(price=price, size=size)
        if side == "ask":
            asks = asks + (level,)
        else:
            bids = bids + (level,)
    return Orderbook(token_id=token, bids=bids, asks=asks, timestamp=NOW)


def test_market_maker_quotes_inside_when_spread_wide():
    mm = MarketMaker(quote_size=10, min_spread_ticks=2)
    snap = MarketSnapshot(
        market=_market(),
        yes_book=_book("yes", bid=0.40, ask=0.50),
        no_book=_book("no", bid=0.50, ask=0.60),
    )
    intents = mm.on_snapshot(snap)
    # Two sides per token, two tokens -> 4 intents when spread is wide.
    assert len(intents) == 4
    sides = {(i.token_id, i.side) for i in intents}
    assert ("yes", Side.BUY) in sides and ("yes", Side.SELL) in sides


def test_market_maker_silent_on_tight_spread():
    mm = MarketMaker(min_spread_ticks=3)
    snap = MarketSnapshot(
        market=_market(),
        yes_book=_book("yes", bid=0.49, ask=0.50),  # 1 tick
        no_book=_book("no", bid=0.49, ask=0.50),
    )
    assert mm.on_snapshot(snap) == ()


def test_yes_no_arb_sells_when_bids_sum_above_one():
    arb = YesNoArb(min_edge=0.005)
    snap = MarketSnapshot(
        market=_market(),
        yes_book=_book("yes", bid=0.55, ask=0.60),
        no_book=_book("no", bid=0.50, ask=0.55),  # 0.55 + 0.50 = 1.05 -> sell both
    )
    intents = arb.on_snapshot(snap)
    assert len(intents) == 2
    assert all(i.side is Side.SELL for i in intents)


def test_yes_no_arb_buys_when_asks_sum_below_one():
    arb = YesNoArb(min_edge=0.005)
    snap = MarketSnapshot(
        market=_market(),
        yes_book=_book("yes", bid=0.40, ask=0.42),
        no_book=_book("no", bid=0.50, ask=0.52),  # 0.42 + 0.52 = 0.94 -> buy both
    )
    intents = arb.on_snapshot(snap)
    assert len(intents) == 2
    assert all(i.side is Side.BUY for i in intents)


def test_yes_no_arb_silent_when_book_balanced():
    arb = YesNoArb(min_edge=0.005)
    snap = MarketSnapshot(
        market=_market(),
        yes_book=_book("yes", bid=0.49, ask=0.51),
        no_book=_book("no", bid=0.49, ask=0.51),
    )
    assert arb.on_snapshot(snap) == ()


def test_signal_model_emits_long_on_momentum_with_imbalance():
    sm = SignalModel(ema_alpha=1.0, momentum_threshold=0.0, book_imbalance_min=1.0)
    snap = MarketSnapshot(
        market=_market(),
        yes_book=_book("yes", bid=0.49, ask=0.51, bid_size=10, ask_size=100),
        no_book=_book("no", bid=0.49, ask=0.51, bid_size=100, ask_size=10),
    )
    # With alpha=1, EMA equals current mid -> mid - ema == 0, threshold not exceeded.
    assert sm.on_snapshot(snap) == ()
