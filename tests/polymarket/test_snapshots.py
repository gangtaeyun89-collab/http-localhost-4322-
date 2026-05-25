from datetime import datetime, timedelta, timezone

import pytest

from quant_tool.polymarket.data.models import (
    Market,
    Orderbook,
    OrderbookLevel,
    Token,
)
from quant_tool.polymarket.data.snapshots import (
    SCHEMA_VERSION,
    append_batch,
    deserialize_snapshot,
    dump_snapshots,
    iter_batches,
    load_snapshots,
    serialize_snapshot,
)
from quant_tool.polymarket.strategy.base import MarketSnapshot


def _market() -> Market:
    return Market(
        condition_id="cond-1",
        question="Will X happen?",
        tokens=(Token(token_id="yes", outcome="Yes"), Token(token_id="no", outcome="No")),
        tick_size=0.01,
        min_order_size=5.0,
        end_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
        closed=False,
        active=True,
    )


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        market=_market(),
        yes_book=Orderbook(
            token_id="yes",
            bids=(OrderbookLevel(price=0.49, size=100),),
            asks=(OrderbookLevel(price=0.51, size=80),),
            timestamp=datetime(2026, 5, 24, 12, tzinfo=timezone.utc),
        ),
        no_book=Orderbook(
            token_id="no",
            bids=(OrderbookLevel(price=0.48, size=120),),
            asks=(OrderbookLevel(price=0.52, size=90),),
            timestamp=datetime(2026, 5, 24, 12, tzinfo=timezone.utc),
        ),
    )


def test_round_trip_preserves_all_fields():
    snap = _snapshot()
    payload = serialize_snapshot(snap)
    restored = deserialize_snapshot(payload)
    assert restored.market.condition_id == snap.market.condition_id
    assert restored.market.tick_size == snap.market.tick_size
    assert restored.market.end_date == snap.market.end_date
    assert restored.yes_book.best_bid().price == 0.49
    assert restored.no_book.best_ask().size == 90
    assert restored.yes_book.timestamp == snap.yes_book.timestamp


def test_dump_and_load_writes_versioned_file(tmp_path):
    target = tmp_path / "snap.json"
    dump_snapshots([_snapshot()], target, universe_size=42)
    loaded = load_snapshots(target)
    assert len(loaded.snapshots) == 1
    assert loaded.universe_size == 42
    # Schema version is embedded; bumping it should fail the loader.
    import json
    payload = json.loads(target.read_text())
    assert payload["schema_version"] == SCHEMA_VERSION
    payload["schema_version"] = 999
    target.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="schema version"):
        load_snapshots(target)


def test_snapshot_with_trades_round_trip():
    from quant_tool.polymarket.data.models import Trade
    snap_with_trades = MarketSnapshot(
        market=_market(),
        yes_book=_snapshot().yes_book,
        no_book=_snapshot().no_book,
        trades=(
            Trade(token_id="yes", price=0.50, size=10, side="BUY",
                  timestamp=datetime(2026, 5, 24, 12, tzinfo=timezone.utc)),
            Trade(token_id="no", price=0.49, size=5, side="SELL",
                  timestamp=datetime(2026, 5, 24, 12, 1, tzinfo=timezone.utc)),
        ),
    )
    restored = deserialize_snapshot(serialize_snapshot(snap_with_trades))
    assert len(restored.trades) == 2
    assert restored.trades[0].price == 0.50
    assert restored.trades[1].side == "SELL"


def test_snapshot_without_trades_omits_field():
    """Back-compat: old files have no `trades` key; new files only include it when non-empty."""
    snap = _snapshot()
    payload = serialize_snapshot(snap)
    assert "trades" not in payload
    restored = deserialize_snapshot(payload)
    assert restored.trades == ()


def test_jsonl_round_trip(tmp_path):
    path = tmp_path / "series.jsonl"
    t1 = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 5, 24, 12, 2, tzinfo=timezone.utc)
    append_batch(path, [_snapshot()], captured_at=t1, universe_size=10)
    append_batch(path, [_snapshot(), _snapshot()], captured_at=t2, universe_size=11)
    batches = list(iter_batches(path))
    assert len(batches) == 2
    assert batches[0].captured_at == t1
    assert batches[0].universe_size == 10
    assert len(batches[0].snapshots) == 1
    assert batches[1].captured_at == t2
    assert len(batches[1].snapshots) == 2


def test_iter_batches_skip_fast_forwards_without_parsing(tmp_path):
    """skip=N must drop the first N lines and yield only the rest."""
    path = tmp_path / "series.jsonl"
    t0 = datetime(2026, 5, 24, 12, tzinfo=timezone.utc)
    for i in range(5):
        append_batch(path, [_snapshot()],
                      captured_at=t0 + timedelta(minutes=i), universe_size=10)
    full = list(iter_batches(path))
    skipped = list(iter_batches(path, skip=3))
    assert len(full) == 5
    assert len(skipped) == 2
    # Skipped result should match the last 2 batches of the full result.
    assert skipped[0].captured_at == full[3].captured_at
    assert skipped[1].captured_at == full[4].captured_at


def test_iter_batches_skip_beyond_file_yields_nothing(tmp_path):
    path = tmp_path / "series.jsonl"
    append_batch(path, [_snapshot()])
    assert list(iter_batches(path, skip=99)) == []


def test_jsonl_skips_partial_trailing_line(tmp_path):
    """A crashed capture can leave a half-written final line; loader skips it."""
    path = tmp_path / "series.jsonl"
    append_batch(path, [_snapshot()])
    # Simulate a crash mid-write by appending a truncated JSON line.
    with path.open("a") as fh:
        fh.write('{"schema_version": 1, "captured_at": "2026-')
    batches = list(iter_batches(path))
    assert len(batches) == 1  # the good line survives, the partial is ignored


def test_load_handles_market_with_no_end_date(tmp_path):
    snap = MarketSnapshot(
        market=Market(
            condition_id="c",
            question="q",
            tokens=(Token(token_id="y", outcome="Yes"), Token(token_id="n", outcome="No")),
            tick_size=0.01,
            min_order_size=5.0,
            end_date=None,
            closed=False,
            active=True,
        ),
        yes_book=Orderbook(token_id="y", bids=(), asks=(), timestamp=datetime.now(timezone.utc)),
        no_book=Orderbook(token_id="n", bids=(), asks=(), timestamp=datetime.now(timezone.utc)),
    )
    target = tmp_path / "snap.json"
    dump_snapshots([snap], target)
    loaded = load_snapshots(target)
    assert loaded.snapshots[0].market.end_date is None
    assert loaded.snapshots[0].yes_book.bids == ()
