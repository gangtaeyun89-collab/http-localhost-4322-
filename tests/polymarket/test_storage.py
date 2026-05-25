from datetime import datetime, timedelta, timezone

import pytest

from quant_tool.polymarket.storage import Storage


def _make_storage(tmp_path) -> Storage:
    return Storage(tmp_path / "test.sqlite")


def test_start_run_assigns_id_and_heartbeats(tmp_path):
    s = _make_storage(tmp_path)
    rid = s.start_run(mode="paper", bankroll=10_000, config={"x": 1}, pid=42)
    assert rid >= 1
    run = s.get_run(rid)
    assert run is not None
    assert run.mode == "paper"
    assert run.bankroll == 10_000
    assert run.pid == 42
    assert run.cycles_completed == 0
    assert run.is_alive is True


def test_end_run_sets_ended_at(tmp_path):
    s = _make_storage(tmp_path)
    rid = s.start_run(mode="paper", bankroll=1000)
    s.end_run(rid)
    run = s.get_run(rid)
    assert run.ended_at is not None
    assert run.is_alive is False


def test_record_and_query_fills(tmp_path):
    s = _make_storage(tmp_path)
    rid = s.start_run(mode="paper", bankroll=1000)
    t0 = datetime(2026, 5, 24, 12, tzinfo=timezone.utc)
    s.record_fill(rid, timestamp=t0, strategy="market_maker", token_id="tok",
                   condition_id="cond", side="BUY", price=0.45, size=10,
                   post_only=False, fill_type="immediate")
    s.record_fill(rid, timestamp=t0 + timedelta(minutes=1), strategy="arb_yes_no",
                   token_id="tok2", condition_id="cond2", side="SELL", price=0.55,
                   size=20, post_only=True, fill_type="rested")
    fills = s.fills_for_run(rid)
    assert len(fills) == 2
    # ORDER BY timestamp DESC -> most recent first
    assert fills[0].strategy == "arb_yes_no"
    assert fills[1].price == 0.45


def test_fills_since_filters_correctly(tmp_path):
    s = _make_storage(tmp_path)
    rid = s.start_run(mode="paper", bankroll=1000)
    t0 = datetime(2026, 5, 24, 12, tzinfo=timezone.utc)
    s.record_fill(rid, timestamp=t0, strategy="s", token_id="t", condition_id="c",
                   side="BUY", price=0.5, size=1, post_only=False, fill_type="immediate")
    s.record_fill(rid, timestamp=t0 + timedelta(minutes=5), strategy="s", token_id="t",
                   condition_id="c", side="SELL", price=0.6, size=1, post_only=False,
                   fill_type="immediate")
    since = t0 + timedelta(minutes=2)
    fills = s.fills_for_run(rid, since=since)
    assert len(fills) == 1
    assert fills[0].side == "SELL"


def test_equity_records_in_chronological_order(tmp_path):
    s = _make_storage(tmp_path)
    rid = s.start_run(mode="paper", bankroll=1000)
    t0 = datetime(2026, 5, 24, 12, tzinfo=timezone.utc)
    for i in range(3):
        s.record_equity(rid, timestamp=t0 + timedelta(minutes=i),
                         cash=1000 - i, total_equity=1000 + i,
                         realised_pnl=i, unrealised_pnl=0)
    rows = s.equity_for_run(rid)
    assert [r.total_equity for r in rows] == [1000, 1001, 1002]


def test_position_upsert(tmp_path):
    s = _make_storage(tmp_path)
    rid = s.start_run(mode="paper", bankroll=1000)
    s.upsert_position(rid, token_id="tok", condition_id="cond", shares=10,
                       avg_price=0.4, realised_pnl=0)
    s.upsert_position(rid, token_id="tok", condition_id="cond", shares=5,
                       avg_price=0.42, realised_pnl=0.5)
    positions = s.positions_for_run(rid)
    assert len(positions) == 1
    assert positions[0].shares == 5
    assert positions[0].avg_price == 0.42
    assert positions[0].realised_pnl == 0.5


def test_positions_open_only(tmp_path):
    s = _make_storage(tmp_path)
    rid = s.start_run(mode="paper", bankroll=1000)
    s.upsert_position(rid, token_id="a", condition_id="c", shares=10, avg_price=0.5, realised_pnl=0)
    s.upsert_position(rid, token_id="b", condition_id="c", shares=0,  avg_price=0,   realised_pnl=2)
    assert len(s.positions_for_run(rid)) == 2
    assert len(s.positions_for_run(rid, open_only=True)) == 1


def test_is_alive_window(tmp_path):
    s = _make_storage(tmp_path)
    rid = s.start_run(mode="paper", bankroll=1000)
    s.heartbeat(rid, 3)
    run = s.get_run(rid)
    assert run.is_alive is True
    assert run.cycles_completed == 3
    # Manually backdate the heartbeat past the 120s window
    s._conn.execute("UPDATE runs SET last_heartbeat_at = ? WHERE id = ?",
                    ((datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(), rid))
    run = s.get_run(rid)
    assert run.is_alive is False


def test_wal_journal_mode_active(tmp_path):
    s = _make_storage(tmp_path)
    cur = s._conn.execute("PRAGMA journal_mode")
    assert cur.fetchone()[0] == "wal"
