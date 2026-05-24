from datetime import datetime, timezone

import pytest

from quant_tool.polymarket.data.models import (
    Market,
    Orderbook,
    OrderbookLevel,
    Token,
)
from quant_tool.polymarket.data.snapshots import (
    SCHEMA_VERSION,
    deserialize_snapshot,
    dump_snapshots,
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
