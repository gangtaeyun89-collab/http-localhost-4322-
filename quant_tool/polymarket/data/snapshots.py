"""JSON serialization for captured market snapshots.

The smoke script writes a single batch (one JSON object per file); the recurring
capture writes a series as JSON-Lines (one batch object per line). The replay
scripts read either format back. Keeping the load/dump pair in one module means
changes to the format are caught at import time, not at file-open time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from quant_tool.polymarket.data.models import (
    Market,
    Orderbook,
    OrderbookLevel,
    Token,
)
from quant_tool.polymarket.strategy.base import MarketSnapshot


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SnapshotBatch:
    """One capture cycle: all snapshots fetched at a single point in time."""

    captured_at: datetime
    universe_size: int
    snapshots: tuple[MarketSnapshot, ...]


# Back-compat alias: the single-file format was previously exposed as
# ``SnapshotFile`` and a few tests still import it under that name.
SnapshotFile = SnapshotBatch


# ---------- single-batch JSON (used by the smoke script's --save) -------


def dump_snapshots(
    snapshots: Iterable[MarketSnapshot],
    path: str | Path,
    *,
    universe_size: int | None = None,
    captured_at: datetime | None = None,
) -> None:
    """Write one batch as a pretty-printed JSON object (``snapshot.json`` style)."""
    payload = serialize_batch(tuple(snapshots), captured_at=captured_at,
                              universe_size=universe_size)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2))


def serialize_batch(
    snapshots: tuple[MarketSnapshot, ...],
    *,
    captured_at: datetime | None = None,
    universe_size: int | None = None,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "captured_at": (captured_at or datetime.now(timezone.utc)).isoformat(),
        "universe_size": universe_size if universe_size is not None else len(snapshots),
        "snapshots": [serialize_snapshot(s) for s in snapshots],
    }


def serialize_snapshot(snap: MarketSnapshot) -> dict:
    return {
        "market": _serialize_market(snap.market),
        "yes_book": _serialize_book(snap.yes_book),
        "no_book": _serialize_book(snap.no_book),
    }


def _serialize_market(market: Market) -> dict:
    return {
        "condition_id": market.condition_id,
        "question": market.question,
        "tick_size": market.tick_size,
        "min_order_size": market.min_order_size,
        "end_date": market.end_date.isoformat() if market.end_date else None,
        "closed": market.closed,
        "active": market.active,
        "tokens": [{"token_id": t.token_id, "outcome": t.outcome} for t in market.tokens],
    }


def _serialize_book(book: Orderbook) -> dict:
    return {
        "token_id": book.token_id,
        "timestamp": book.timestamp.isoformat(),
        "bids": [{"price": lvl.price, "size": lvl.size} for lvl in book.bids],
        "asks": [{"price": lvl.price, "size": lvl.size} for lvl in book.asks],
    }


# ---------- load --------------------------------------------------------


def load_snapshots(path: str | Path) -> SnapshotFile:
    payload = json.loads(Path(path).read_text())
    version = payload.get("schema_version", 1)
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported snapshot schema version {version} (expected {SCHEMA_VERSION})"
        )
    snapshots = tuple(deserialize_snapshot(raw) for raw in payload.get("snapshots", []))
    return SnapshotFile(
        snapshots=snapshots,
        captured_at=_parse_iso(payload.get("captured_at")) or datetime.now(timezone.utc),
        universe_size=int(payload.get("universe_size", len(snapshots))),
    )


def deserialize_snapshot(raw: dict) -> MarketSnapshot:
    market = _deserialize_market(raw["market"])
    yes_book = _deserialize_book(raw["yes_book"])
    no_book = _deserialize_book(raw["no_book"])
    return MarketSnapshot(market=market, yes_book=yes_book, no_book=no_book)


def _deserialize_market(raw: dict) -> Market:
    tokens = tuple(Token(token_id=t["token_id"], outcome=t["outcome"]) for t in raw["tokens"])
    return Market(
        condition_id=raw["condition_id"],
        question=raw["question"],
        tokens=tokens,
        tick_size=float(raw["tick_size"]),
        min_order_size=float(raw["min_order_size"]),
        end_date=_parse_iso(raw.get("end_date")),
        closed=bool(raw.get("closed", False)),
        active=bool(raw.get("active", True)),
    )


def _deserialize_book(raw: dict) -> Orderbook:
    bids = tuple(OrderbookLevel(price=float(b["price"]), size=float(b["size"]))
                 for b in raw.get("bids", []))
    asks = tuple(OrderbookLevel(price=float(a["price"]), size=float(a["size"]))
                 for a in raw.get("asks", []))
    return Orderbook(
        token_id=raw["token_id"],
        bids=bids,
        asks=asks,
        timestamp=_parse_iso(raw.get("timestamp")) or datetime.now(timezone.utc),
    )


def _parse_iso(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------- JSON-Lines stream (used by the recurring capture) -----------


def append_batch(
    path: str | Path,
    snapshots: Iterable[MarketSnapshot],
    *,
    captured_at: datetime | None = None,
    universe_size: int | None = None,
) -> None:
    """Append one capture cycle as a single JSONL line.

    Crash-safe-enough for our purposes: each line is a complete JSON object, so
    a partial line at the end of the file just gets dropped by :func:`iter_batches`.
    """
    payload = serialize_batch(tuple(snapshots), captured_at=captured_at,
                              universe_size=universe_size)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as fh:
        fh.write(json.dumps(payload) + "\n")


def iter_batches(path: str | Path) -> Iterator[SnapshotBatch]:
    """Yield each batch from a JSONL capture in file order.

    Partial / unparseable lines are silently skipped so a crashed capture
    doesn't poison the rest of the series.
    """
    with Path(path).open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            version = payload.get("schema_version", 1)
            if version != SCHEMA_VERSION:
                raise ValueError(
                    f"unsupported snapshot schema version {version} (expected {SCHEMA_VERSION})"
                )
            snapshots = tuple(deserialize_snapshot(raw) for raw in payload.get("snapshots", []))
            yield SnapshotBatch(
                captured_at=_parse_iso(payload.get("captured_at")) or datetime.now(timezone.utc),
                universe_size=int(payload.get("universe_size", len(snapshots))),
                snapshots=snapshots,
            )
