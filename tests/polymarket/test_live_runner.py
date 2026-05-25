"""LiveRunner uses injected clients so it doesn't need network."""

from datetime import datetime, timezone

import pytest

from quant_tool.polymarket.data.models import (
    Market,
    Orderbook,
    OrderbookLevel,
    Token,
    Trade,
)
from quant_tool.polymarket.live_runner import LiveRunner, LiveRunnerConfig
from quant_tool.polymarket.storage import Storage


class _FakeGamma:
    def __init__(self, markets):
        self.markets = markets

    def active_markets(self, limit=200):
        return self.markets


class _FakeClob:
    def __init__(self, books, trades=None):
        self.books = books          # token_id -> Orderbook
        self.trades_ = trades or {}  # token_id -> tuple[Trade, ...]

    def orderbook(self, token_id):
        return self.books[token_id]

    def trades(self, token_id, limit=50):
        return self.trades_.get(token_id, ())


def _market(cid="c1"):
    return Market(
        condition_id=cid, question="q",
        tokens=(Token(token_id=f"y_{cid}", outcome="Yes"),
                Token(token_id=f"n_{cid}", outcome="No")),
        tick_size=0.01, min_order_size=5.0, end_date=None, closed=False, active=True,
    )


def _book(tid, bid, ask):
    return Orderbook(
        token_id=tid,
        bids=(OrderbookLevel(price=bid, size=100),),
        asks=(OrderbookLevel(price=ask, size=100),),
        timestamp=datetime.now(timezone.utc),
    )


def test_tick_persists_equity_each_cycle(tmp_path):
    markets = [_market("c1")]
    books = {"y_c1": _book("y_c1", 0.40, 0.50), "n_c1": _book("n_c1", 0.50, 0.60)}
    config = LiveRunnerConfig(
        db_path=str(tmp_path / "live.sqlite"),
        bankroll=1_000, interval_seconds=0.001, markets_per_cycle=1,
        strategy_names=("market_maker",), max_per_market=0.5, max_total=1.0,
    )
    runner = LiveRunner(config, clob=_FakeClob(books), gamma=_FakeGamma(markets))
    runner.start()
    runner.tick(0)
    rows = runner.storage.equity_for_run(runner.run_id)
    assert len(rows) == 1
    assert rows[0].total_equity == 1_000.0


def test_tick_persists_fill_via_trade_print(tmp_path):
    markets = [_market("c1")]
    books = {"y_c1": _book("y_c1", 0.40, 0.50), "n_c1": _book("n_c1", 0.50, 0.60)}
    # Note: MarketMaker quotes at mid +/- 1 tick = BUY 0.44 / SELL 0.46. A print at 0.44
    # only credits the resting BUY if it's already resting -- so we need two ticks: first
    # to plant the resting order, second to feed in the print.
    config = LiveRunnerConfig(
        db_path=str(tmp_path / "live.sqlite"),
        bankroll=1_000, interval_seconds=0.001, markets_per_cycle=1,
        strategy_names=("market_maker",), max_per_market=0.5, max_total=1.0,
    )
    clob = _FakeClob(books)
    runner = LiveRunner(config, clob=clob, gamma=_FakeGamma(markets))
    runner.start()
    runner.tick(0)  # plants the MM quotes

    # Cycle 2: same books, plus a print at 0.44 on the YES token
    trade = Trade(token_id="y_c1", price=0.44, size=10, side="SELL",
                   timestamp=datetime.now(timezone.utc))
    clob.trades_ = {"y_c1": (trade,)}
    runner.tick(1)

    fills = runner.storage.fills_for_run(runner.run_id)
    assert any(f.fill_type == "rested" and f.price == 0.44 for f in fills)
    positions = runner.storage.positions_for_run(runner.run_id, open_only=True)
    assert any(p.token_id == "y_c1" and p.shares > 0 for p in positions)


def test_tick_writes_capture_when_configured(tmp_path):
    """Live bot should append each cycle to the capture JSONL for the Backtest page."""
    from quant_tool.polymarket.data.snapshots import iter_batches
    markets = [_market("c1")]
    books = {"y_c1": _book("y_c1", 0.40, 0.50), "n_c1": _book("n_c1", 0.50, 0.60)}
    capture = tmp_path / "live_capture.jsonl"
    config = LiveRunnerConfig(
        db_path=str(tmp_path / "live.sqlite"),
        bankroll=1_000, interval_seconds=0.001, markets_per_cycle=1,
        strategy_names=("market_maker",), max_per_market=0.5, max_total=1.0,
        capture_path=str(capture),
    )
    runner = LiveRunner(config, clob=_FakeClob(books), gamma=_FakeGamma(markets))
    runner.start()
    runner.tick(0)
    runner.tick(1)
    assert capture.exists()
    batches = list(iter_batches(capture))
    assert len(batches) == 2
    assert len(batches[0].snapshots) == 1


def test_tick_capture_every_n_cycles(tmp_path):
    from quant_tool.polymarket.data.snapshots import iter_batches
    markets = [_market("c1")]
    books = {"y_c1": _book("y_c1", 0.40, 0.50), "n_c1": _book("n_c1", 0.50, 0.60)}
    capture = tmp_path / "live_capture.jsonl"
    config = LiveRunnerConfig(
        db_path=str(tmp_path / "live.sqlite"),
        bankroll=1_000, interval_seconds=0.001, markets_per_cycle=1,
        strategy_names=("market_maker",), max_per_market=0.5, max_total=1.0,
        capture_path=str(capture), capture_every_n_cycles=3,
    )
    runner = LiveRunner(config, clob=_FakeClob(books), gamma=_FakeGamma(markets))
    runner.start()
    for i in range(5):
        runner.tick(i)
    batches = list(iter_batches(capture))
    # Cycles 0 and 3 hit the every-N filter; 1, 2, 4 should not.
    assert len(batches) == 2


def test_tick_records_cycle_metric(tmp_path):
    """Every tick should persist a cycle_metric row -- powers the dashboard chart."""
    markets = [_market("c1")]
    books = {"y_c1": _book("y_c1", 0.40, 0.50), "n_c1": _book("n_c1", 0.50, 0.60)}
    config = LiveRunnerConfig(
        db_path=str(tmp_path / "live.sqlite"),
        bankroll=1_000, interval_seconds=0.001, markets_per_cycle=1,
        strategy_names=("market_maker",), max_per_market=0.5, max_total=1.0,
    )
    runner = LiveRunner(config, clob=_FakeClob(books), gamma=_FakeGamma(markets))
    runner.start()
    runner.tick(0)
    runner.tick(1)
    metrics = runner.storage.cycle_metrics_for_run(runner.run_id)
    assert len(metrics) == 2
    # market_maker quotes 4 sides on a wide spread (BUY/SELL on YES+NO).
    assert metrics[0].intents_generated >= 4
    assert metrics[0].snapshots_seen == 1
    assert metrics[0].universe_size == 1


def test_run_id_lifecycle(tmp_path):
    config = LiveRunnerConfig(db_path=str(tmp_path / "live.sqlite"),
                               bankroll=1_000, interval_seconds=0.001,
                               markets_per_cycle=1)
    runner = LiveRunner(config, clob=_FakeClob({}), gamma=_FakeGamma([]))
    rid = runner.start()
    assert runner.storage.get_run(rid).is_alive is True
    runner.stop()
    assert runner.storage.get_run(rid).is_alive is False


def test_live_mode_rejected_until_clob_broker_exists(tmp_path):
    with pytest.raises(ValueError, match="live mode requires ClobBroker"):
        LiveRunnerConfig(db_path=str(tmp_path / "x.sqlite"), mode="live")
