from datetime import datetime, timezone

from quant_tool.polymarket.data.models import Orderbook, OrderbookLevel
from quant_tool.polymarket.execution.paper_broker import PaperBroker, Position
from quant_tool.polymarket.strategy.base import Intent, Side


NOW = datetime(2026, 5, 24, tzinfo=timezone.utc)


def _book(token="tok", bid=0.49, bid_size=100, ask=0.51, ask_size=100):
    return Orderbook(
        token_id=token,
        bids=(OrderbookLevel(price=bid, size=bid_size),),
        asks=(OrderbookLevel(price=ask, size=ask_size),),
        timestamp=NOW,
    )


def test_taker_buy_fills_immediately_at_ask():
    broker = PaperBroker(starting_cash=1000)
    intent = Intent("s", "tok", Side.BUY, price=0.55, size=10, post_only=False)
    fill = broker.submit(intent, _book(), now=NOW)
    assert fill is not None
    assert fill.price == 0.51
    assert fill.size == 10
    assert broker.cash == 1000 - 0.51 * 10
    assert broker.positions["tok"].shares == 10


def test_taker_size_capped_by_resting_size():
    broker = PaperBroker(starting_cash=1000)
    intent = Intent("s", "tok", Side.BUY, price=0.55, size=500, post_only=False)
    fill = broker.submit(intent, _book(ask_size=20), now=NOW)
    assert fill is not None
    assert fill.size == 20


def test_post_only_below_ask_rests():
    broker = PaperBroker(starting_cash=1000)
    intent = Intent("s", "tok", Side.BUY, price=0.48, size=10, post_only=True)
    fill = broker.submit(intent, _book(), now=NOW)
    assert fill is None
    assert len(broker.open_orders) == 1


def test_post_only_that_would_cross_is_rejected():
    broker = PaperBroker(starting_cash=1000)
    intent = Intent("s", "tok", Side.BUY, price=0.52, size=10, post_only=True)
    assert broker.submit(intent, _book(), now=NOW) is None
    assert broker.open_orders == {}  # rejected, not rested


def test_resting_order_fills_on_book_update():
    broker = PaperBroker(starting_cash=1000)
    intent = Intent("s", "tok", Side.BUY, price=0.48, size=10, post_only=True)
    broker.submit(intent, _book(), now=NOW)
    # New book has an ask at 0.48 -- our 0.48 bid should fill.
    new_book = _book(ask=0.48, ask_size=10)
    fills = broker.on_book(new_book, now=NOW)
    assert len(fills) == 1
    assert fills[0].price == 0.48
    assert broker.open_orders == {}


def test_position_realises_pnl_on_close():
    pos = Position()
    pos.apply(Side.BUY, 0.40, 100)   # long 100 @ 0.40
    pos.apply(Side.SELL, 0.55, 100)  # close at 0.55
    assert pos.shares == 0
    assert abs(pos.realised_pnl - 15.0) < 1e-9  # (0.55 - 0.40) * 100


def test_equity_marks_open_position_to_mid():
    broker = PaperBroker(starting_cash=1000)
    broker.submit(Intent("s", "tok", Side.BUY, 0.55, 100, post_only=False), _book(), now=NOW)
    # Bought 100 @ 0.51 -> cash 949, position 100 shares.
    equity = broker.equity({"tok": 0.60})
    assert abs(equity - (949.0 + 100 * 0.60)) < 1e-9
