"""Tests for the backtest library function used by both CLI and dashboard."""

from datetime import datetime, timedelta, timezone

from quant_tool.polymarket.backtest import run_backtest
from quant_tool.polymarket.data.models import (
    Market,
    Orderbook,
    OrderbookLevel,
    Token,
    Trade,
)
from quant_tool.polymarket.data.snapshots import append_batch
from quant_tool.polymarket.strategy.base import MarketSnapshot


def _market(cid="c1"):
    return Market(
        condition_id=cid, question=f"market {cid}",
        tokens=(Token(token_id=f"y_{cid}", outcome="Yes"),
                Token(token_id=f"n_{cid}", outcome="No")),
        tick_size=0.01, min_order_size=5.0, end_date=None, closed=False, active=True,
    )


def _book(tid, bid, ask, ts):
    return Orderbook(
        token_id=tid,
        bids=(OrderbookLevel(price=bid, size=100),),
        asks=(OrderbookLevel(price=ask, size=100),),
        timestamp=ts,
    )


def test_run_backtest_on_quiet_capture_returns_zero_fills(tmp_path):
    """Replaying a capture where books don't move yields zero fills, no errors."""
    cap = tmp_path / "quiet.jsonl"
    t0 = datetime(2026, 5, 24, 12, tzinfo=timezone.utc)
    for i in range(3):
        ts = t0 + timedelta(minutes=2 * i)
        append_batch(cap, [
            MarketSnapshot(
                market=_market("c1"),
                yes_book=_book("y_c1", 0.40, 0.50, ts),
                no_book=_book("n_c1", 0.49, 0.51, ts),
            )
        ], captured_at=ts, universe_size=1)

    result = run_backtest(cap, strategy_names=["market_maker", "arb_yes_no"],
                          bankroll=1000, max_per_market=0.5, max_total=1.0)
    assert result.batches == 3
    assert result.snapshots == 3
    assert result.final_equity == 1000.0
    assert result.realised_pnl == 0.0
    assert all(s.immediate_fills + s.rested_fills == 0
               for s in result.stats_by_strategy.values())


def test_run_backtest_credits_print_fill(tmp_path):
    """A print at our resting bid should fill us even if the book looks unchanged."""
    cap = tmp_path / "with_trade.jsonl"
    t0 = datetime(2026, 5, 24, 12, tzinfo=timezone.utc)

    # T0: MM quotes around mid 0.45 (BUY 0.44, SELL 0.46)
    append_batch(cap, [
        MarketSnapshot(market=_market("c1"),
                       yes_book=_book("y_c1", 0.40, 0.50, t0),
                       no_book=_book("n_c1", 0.49, 0.51, t0))
    ], captured_at=t0, universe_size=1)

    # T1: same book, but a print at 0.44 should credit our resting BUY
    trade = Trade(token_id="y_c1", price=0.44, size=15, side="SELL",
                   timestamp=t0 + timedelta(seconds=30))
    append_batch(cap, [
        MarketSnapshot(market=_market("c1"),
                       yes_book=_book("y_c1", 0.40, 0.50, t0 + timedelta(minutes=2)),
                       no_book=_book("n_c1", 0.49, 0.51, t0 + timedelta(minutes=2)),
                       trades=(trade,))
    ], captured_at=t0 + timedelta(minutes=2), universe_size=1)

    result = run_backtest(cap, strategy_names=["market_maker"], bankroll=1000,
                          max_per_market=0.5, max_total=1.0)
    assert result.prints_seen == 1
    mm = result.stats_by_strategy["market_maker"]
    assert mm.rested_fills == 1
    assert mm.notional_filled > 0


def test_run_backtest_max_batches_replays_only_last_n(tmp_path):
    """max_batches must cap replay length and pick the most recent batches."""
    cap = tmp_path / "long.jsonl"
    t0 = datetime(2026, 5, 24, 12, tzinfo=timezone.utc)
    for i in range(10):
        ts = t0 + timedelta(minutes=2 * i)
        append_batch(cap, [
            MarketSnapshot(market=_market("c1"),
                           yes_book=_book("y_c1", 0.40, 0.50, ts),
                           no_book=_book("n_c1", 0.49, 0.51, ts))
        ], captured_at=ts, universe_size=1)

    result = run_backtest(cap, strategy_names=["market_maker"],
                          bankroll=1000, max_per_market=0.5, max_total=1.0,
                          max_batches=3)
    assert result.batches == 3
    # The equity curve's timestamps should be from the LAST 3 batches.
    last_ts = result.equity_curve[-1].timestamp
    assert last_ts == t0 + timedelta(minutes=18)  # 10th batch (2 * 9)


def test_run_backtest_progress_callback_fires_per_batch(tmp_path):
    cap = tmp_path / "ten.jsonl"
    t0 = datetime(2026, 5, 24, 12, tzinfo=timezone.utc)
    for i in range(5):
        ts = t0 + timedelta(minutes=i)
        append_batch(cap, [
            MarketSnapshot(market=_market("c1"),
                           yes_book=_book("y_c1", 0.40, 0.50, ts),
                           no_book=_book("n_c1", 0.49, 0.51, ts))
        ], captured_at=ts, universe_size=1)

    seen = []
    def cb(done, total): seen.append((done, total))
    run_backtest(cap, strategy_names=["market_maker"], bankroll=1000,
                 max_per_market=0.5, max_total=1.0, progress_callback=cb)
    assert seen == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]


def test_run_backtest_respects_strategy_overrides(tmp_path):
    """min_spread_ticks=10 should suppress all MM intents on a 2-cent-spread book."""
    cap = tmp_path / "wide.jsonl"
    t0 = datetime(2026, 5, 24, 12, tzinfo=timezone.utc)
    append_batch(cap, [
        MarketSnapshot(market=_market("c1"),
                       yes_book=_book("y_c1", 0.49, 0.51, t0),
                       no_book=_book("n_c1", 0.49, 0.51, t0))
    ], captured_at=t0, universe_size=1)

    result = run_backtest(
        cap, strategy_names=["market_maker"],
        strategy_overrides={"market_maker": {"min_spread_ticks": 10}},
        bankroll=1000, max_per_market=0.5, max_total=1.0,
    )
    assert result.stats_by_strategy["market_maker"].intents == 0
