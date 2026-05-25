from datetime import datetime, timezone

from quant_tool.polymarket.data.models import (
    Market,
    Orderbook,
    OrderbookLevel,
    Token,
    Trade,
)
from quant_tool.polymarket.execution.paper_broker import PaperBroker
from quant_tool.polymarket.strategy.base import Intent, MarketSnapshot, Side
from quant_tool.polymarket.strategy.smart_market_maker import SmartMarketMaker


NOW = datetime(2026, 5, 25, tzinfo=timezone.utc)


def _market():
    return Market(
        condition_id="c1", question="q",
        tokens=(Token(token_id="yes", outcome="Yes"),
                Token(token_id="no", outcome="No")),
        tick_size=0.01, min_order_size=5.0, end_date=None, closed=False, active=True,
    )


def _book(tid, bid, ask, bid_size=200, ask_size=200):
    return Orderbook(
        token_id=tid,
        bids=(OrderbookLevel(price=bid, size=bid_size),),
        asks=(OrderbookLevel(price=ask, size=ask_size),),
        timestamp=NOW,
    )


def _snap(yb=(0.40, 0.50), nb=(0.50, 0.60),
           yb_sizes=(200, 200), nb_sizes=(200, 200), trades=()):
    return MarketSnapshot(
        market=_market(),
        yes_book=_book("yes", yb[0], yb[1], *yb_sizes),
        no_book=_book("no", nb[0], nb[1], *nb_sizes),
        trades=trades,
    )


def test_quotes_when_book_is_normal():
    mm = SmartMarketMaker()
    intents = mm.on_snapshot(_snap())
    # Should quote BUY+SELL on both YES and NO
    assert len(intents) == 4
    sides = {(i.token_id, i.side) for i in intents}
    assert (("yes", Side.BUY) in sides and ("yes", Side.SELL) in sides)


def test_skips_extreme_price_markets():
    mm = SmartMarketMaker(min_price=0.05)
    # YES mid = 0.025 -- way below 0.05 threshold
    snap = _snap(yb=(0.02, 0.03), nb=(0.97, 0.98))
    assert mm.on_snapshot(snap) == ()


def test_skips_thin_books():
    mm = SmartMarketMaker(min_book_size=50)
    snap = _snap(yb_sizes=(10, 10), nb_sizes=(10, 10))
    assert mm.on_snapshot(snap) == ()


def test_trade_tape_skew_raises_quotes_on_buy_pressure():
    """If recent prints are mostly BUYs, our quotes should shift UP."""
    mm = SmartMarketMaker(trade_skew_per_imbalance=0.5, max_trade_skew_ticks=5)
    snap_neutral = _snap()
    snap_buys = _snap(trades=(
        Trade("yes", 0.45, 50, "BUY", NOW),
        Trade("yes", 0.46, 30, "BUY", NOW),
    ))
    yes_neutral = [i for i in mm.on_snapshot(snap_neutral) if i.token_id == "yes"]
    mm2 = SmartMarketMaker(trade_skew_per_imbalance=0.5, max_trade_skew_ticks=5)
    yes_buys = [i for i in mm2.on_snapshot(snap_buys) if i.token_id == "yes"]

    # Highest neutral SELL vs highest tape-skewed SELL: skewed should be higher.
    sell_neutral = max(i.price for i in yes_neutral if i.side is Side.SELL)
    sell_buys = max(i.price for i in yes_buys if i.side is Side.SELL)
    assert sell_buys > sell_neutral


def test_inventory_skew_pushes_quotes_against_position():
    mm = SmartMarketMaker(inventory_skew=0.002, max_inventory_shares=10_000)
    mm.inventory["yes"] = 100  # long YES -- should want to sell more, buy less
    intents = [i for i in mm.on_snapshot(_snap()) if i.token_id == "yes"]
    buy = next(i for i in intents if i.side is Side.BUY)
    sell = next(i for i in intents if i.side is Side.SELL)
    # Long inventory -> both quotes shift DOWN (mid - inv_skew*inventory)
    assert buy.price < 0.44   # baseline BUY would be 0.44
    assert sell.price < 0.46  # baseline SELL would be 0.46


def test_max_inventory_only_quotes_reducing_side():
    mm = SmartMarketMaker(max_inventory_shares=50)
    mm.inventory["yes"] = 100  # over cap
    intents = [i for i in mm.on_snapshot(_snap()) if i.token_id == "yes"]
    assert len(intents) == 1
    assert intents[0].side is Side.SELL


def test_signals_cancel_before_quoting():
    """The runner uses this flag to know whether to cancel stale orders."""
    mm = SmartMarketMaker()
    assert mm.cancel_before_quoting is True


def test_broker_cancel_all_for_strategy_filters_correctly():
    broker = PaperBroker(starting_cash=1000)
    # Plant 2 orders from each strategy
    for name in ("smart_market_maker", "market_maker", "smart_market_maker"):
        intent = Intent(strategy=name, token_id="tok", side=Side.BUY,
                         price=0.45, size=10, post_only=True)
        book = _book("tok", 0.40, 0.50)
        broker.submit(intent, book, now=NOW)
    assert len(broker.open_orders) == 3
    cancelled = broker.cancel_all_for_strategy("smart_market_maker")
    assert cancelled == 2
    assert len(broker.open_orders) == 1
    assert next(iter(broker.open_orders.values())).intent.strategy == "market_maker"
