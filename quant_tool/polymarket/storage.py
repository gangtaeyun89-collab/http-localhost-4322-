"""SQLite-backed persistence for live bot runs.

The :class:`Storage` wrapper is the single place that touches the database.
The live runner writes fills, equity snapshots, and position state through it;
the dashboard reads back through the same API. WAL mode lets the dashboard
poll the DB while the runner is writing without blocking either side.

Schema is created on first connect; future migrations would bump
``SCHEMA_VERSION`` and ALTER from there.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RunRow:
    id: int
    started_at: datetime
    ended_at: datetime | None
    mode: str
    bankroll: float
    pid: int | None
    last_heartbeat_at: datetime | None
    cycles_completed: int
    config_json: str

    @property
    def is_alive(self) -> bool:
        """A run is considered alive if it heart-beat in the last 2 minutes."""
        if self.ended_at is not None or self.last_heartbeat_at is None:
            return False
        age = (datetime.now(timezone.utc) - self.last_heartbeat_at).total_seconds()
        return age < 120.0


@dataclass(frozen=True)
class FillRow:
    id: int
    run_id: int
    timestamp: datetime
    strategy: str
    token_id: str
    condition_id: str
    side: str
    price: float
    size: float
    post_only: bool
    fill_type: str  # "immediate" or "rested"


@dataclass(frozen=True)
class EquityRow:
    run_id: int
    timestamp: datetime
    cash: float
    total_equity: float
    realised_pnl: float
    unrealised_pnl: float


@dataclass(frozen=True)
class PositionRow:
    run_id: int
    token_id: str
    condition_id: str
    shares: float
    avg_price: float
    realised_pnl: float
    last_updated: datetime


@dataclass(frozen=True)
class CycleMetricRow:
    """One per cycle the bot completes -- powers the live activity chart."""
    run_id: int
    cycle_number: int
    timestamp: datetime
    universe_size: int
    snapshots_seen: int
    intents_generated: int
    intents_blocked: int
    fills_immediate: int
    fills_rested: int
    elapsed_seconds: float


class Storage:
    """Thin wrapper over a sqlite3 connection. Not thread-safe -- one per process."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, isolation_level=None,
                                      detect_types=sqlite3.PARSE_DECLTYPES)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    # ----- schema -------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.executescript(_SCHEMA_SQL)

    # ----- runs ---------------------------------------------------------

    def start_run(self, *, mode: str, bankroll: float, config: dict | None = None,
                  pid: int | None = None) -> int:
        """Insert a new run row and return its id."""
        cur = self._conn.execute(
            "INSERT INTO runs (started_at, mode, bankroll, pid, last_heartbeat_at, "
            "cycles_completed, config_json) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (
                _now_iso(), mode, float(bankroll), pid,
                _now_iso(),
                json.dumps(config or {}),
            ),
        )
        return int(cur.lastrowid)

    def heartbeat(self, run_id: int, cycles_completed: int) -> None:
        self._conn.execute(
            "UPDATE runs SET last_heartbeat_at = ?, cycles_completed = ? WHERE id = ?",
            (_now_iso(), int(cycles_completed), int(run_id)),
        )

    def end_run(self, run_id: int) -> None:
        self._conn.execute(
            "UPDATE runs SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
            (_now_iso(), int(run_id)),
        )

    def recent_runs(self, limit: int = 20) -> tuple[RunRow, ...]:
        cur = self._conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (int(limit),)
        )
        return tuple(_row_to_run(r) for r in cur)

    def get_run(self, run_id: int) -> RunRow | None:
        cur = self._conn.execute("SELECT * FROM runs WHERE id = ?", (int(run_id),))
        row = cur.fetchone()
        return _row_to_run(row) if row else None

    # ----- fills --------------------------------------------------------

    def record_fill(self, run_id: int, *, timestamp: datetime, strategy: str,
                    token_id: str, condition_id: str, side: str, price: float,
                    size: float, post_only: bool, fill_type: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO fills (run_id, timestamp, strategy, token_id, condition_id, "
            "side, price, size, post_only, fill_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (int(run_id), timestamp.isoformat(), strategy, token_id, condition_id,
             side, float(price), float(size), 1 if post_only else 0, fill_type),
        )
        return int(cur.lastrowid)

    def fills_for_run(self, run_id: int, *, since: datetime | None = None,
                      limit: int | None = None) -> tuple[FillRow, ...]:
        sql = "SELECT * FROM fills WHERE run_id = ?"
        args: list[object] = [int(run_id)]
        if since is not None:
            sql += " AND timestamp > ?"
            args.append(since.isoformat())
        sql += " ORDER BY timestamp DESC"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(int(limit))
        cur = self._conn.execute(sql, args)
        return tuple(_row_to_fill(r) for r in cur)

    # ----- equity -------------------------------------------------------

    def record_equity(self, run_id: int, *, timestamp: datetime, cash: float,
                       total_equity: float, realised_pnl: float,
                       unrealised_pnl: float) -> None:
        self._conn.execute(
            "INSERT INTO equity_snapshots (run_id, timestamp, cash, total_equity, "
            "realised_pnl, unrealised_pnl) VALUES (?, ?, ?, ?, ?, ?)",
            (int(run_id), timestamp.isoformat(), float(cash), float(total_equity),
             float(realised_pnl), float(unrealised_pnl)),
        )

    def equity_for_run(self, run_id: int) -> tuple[EquityRow, ...]:
        cur = self._conn.execute(
            "SELECT * FROM equity_snapshots WHERE run_id = ? ORDER BY timestamp ASC",
            (int(run_id),),
        )
        return tuple(_row_to_equity(r) for r in cur)

    # ----- positions ----------------------------------------------------

    def upsert_position(self, run_id: int, *, token_id: str, condition_id: str,
                        shares: float, avg_price: float, realised_pnl: float) -> None:
        self._conn.execute(
            "INSERT INTO positions (run_id, token_id, condition_id, shares, avg_price, "
            "realised_pnl, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id, token_id) DO UPDATE SET "
            "shares = excluded.shares, avg_price = excluded.avg_price, "
            "realised_pnl = excluded.realised_pnl, last_updated = excluded.last_updated",
            (int(run_id), token_id, condition_id, float(shares), float(avg_price),
             float(realised_pnl), _now_iso()),
        )

    def positions_for_run(self, run_id: int, *, open_only: bool = False
                          ) -> tuple[PositionRow, ...]:
        sql = "SELECT * FROM positions WHERE run_id = ?"
        if open_only:
            sql += " AND shares != 0"
        cur = self._conn.execute(sql, (int(run_id),))
        return tuple(_row_to_position(r) for r in cur)

    # ----- cycle metrics -----------------------------------------------

    def record_cycle_metric(self, run_id: int, *, cycle_number: int,
                             timestamp: datetime, universe_size: int,
                             snapshots_seen: int, intents_generated: int,
                             intents_blocked: int, fills_immediate: int,
                             fills_rested: int, elapsed_seconds: float) -> None:
        self._conn.execute(
            "INSERT INTO cycle_metrics (run_id, cycle_number, timestamp, "
            "universe_size, snapshots_seen, intents_generated, intents_blocked, "
            "fills_immediate, fills_rested, elapsed_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (int(run_id), int(cycle_number), timestamp.isoformat(),
             int(universe_size), int(snapshots_seen), int(intents_generated),
             int(intents_blocked), int(fills_immediate), int(fills_rested),
             float(elapsed_seconds)),
        )

    def cycle_metrics_for_run(self, run_id: int, *, limit: int | None = None
                               ) -> tuple[CycleMetricRow, ...]:
        sql = ("SELECT * FROM cycle_metrics WHERE run_id = ? "
               "ORDER BY cycle_number ASC")
        args: list[object] = [int(run_id)]
        if limit is not None:
            sql += " LIMIT ?"
            args.append(int(limit))
        cur = self._conn.execute(sql, args)
        return tuple(_row_to_cycle_metric(r) for r in cur)


# ---------- module helpers ----------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw)


def _row_to_run(row) -> RunRow:
    return RunRow(
        id=row["id"],
        started_at=_parse_iso(row["started_at"]),
        ended_at=_parse_iso(row["ended_at"]),
        mode=row["mode"],
        bankroll=row["bankroll"],
        pid=row["pid"],
        last_heartbeat_at=_parse_iso(row["last_heartbeat_at"]),
        cycles_completed=row["cycles_completed"],
        config_json=row["config_json"],
    )


def _row_to_fill(row) -> FillRow:
    return FillRow(
        id=row["id"], run_id=row["run_id"], timestamp=_parse_iso(row["timestamp"]),
        strategy=row["strategy"], token_id=row["token_id"],
        condition_id=row["condition_id"], side=row["side"],
        price=row["price"], size=row["size"],
        post_only=bool(row["post_only"]), fill_type=row["fill_type"],
    )


def _row_to_equity(row) -> EquityRow:
    return EquityRow(
        run_id=row["run_id"], timestamp=_parse_iso(row["timestamp"]),
        cash=row["cash"], total_equity=row["total_equity"],
        realised_pnl=row["realised_pnl"], unrealised_pnl=row["unrealised_pnl"],
    )


def _row_to_position(row) -> PositionRow:
    return PositionRow(
        run_id=row["run_id"], token_id=row["token_id"], condition_id=row["condition_id"],
        shares=row["shares"], avg_price=row["avg_price"],
        realised_pnl=row["realised_pnl"], last_updated=_parse_iso(row["last_updated"]),
    )


def _row_to_cycle_metric(row) -> CycleMetricRow:
    return CycleMetricRow(
        run_id=row["run_id"], cycle_number=row["cycle_number"],
        timestamp=_parse_iso(row["timestamp"]),
        universe_size=row["universe_size"], snapshots_seen=row["snapshots_seen"],
        intents_generated=row["intents_generated"],
        intents_blocked=row["intents_blocked"],
        fills_immediate=row["fills_immediate"],
        fills_rested=row["fills_rested"],
        elapsed_seconds=row["elapsed_seconds"],
    )


def default_db_path() -> Path:
    """Where the dashboard and runner look for state by default."""
    override = os.environ.get("POLYMARKET_DB_PATH")
    if override:
        return Path(override)
    return Path("data") / "polymarket.sqlite"


def default_bot_log_path() -> Path:
    """Where the bot writes its activity log; the dashboard tails this."""
    override = os.environ.get("POLYMARKET_BOT_LOG_PATH")
    if override:
        return Path(override)
    # Fly.io mounts /data as a volume and the entrypoint writes there.
    if Path("/data").is_dir():
        return Path("/data/bot.log")
    return Path("data") / "bot.log"


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    mode TEXT NOT NULL,
    bankroll REAL NOT NULL,
    pid INTEGER,
    last_heartbeat_at TEXT,
    cycles_completed INTEGER NOT NULL DEFAULT 0,
    config_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    timestamp TEXT NOT NULL,
    strategy TEXT NOT NULL,
    token_id TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    size REAL NOT NULL,
    post_only INTEGER NOT NULL,
    fill_type TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS fills_run_ts ON fills(run_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    timestamp TEXT NOT NULL,
    cash REAL NOT NULL,
    total_equity REAL NOT NULL,
    realised_pnl REAL NOT NULL,
    unrealised_pnl REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS equity_run_ts ON equity_snapshots(run_id, timestamp);

CREATE TABLE IF NOT EXISTS positions (
    run_id INTEGER NOT NULL REFERENCES runs(id),
    token_id TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    shares REAL NOT NULL,
    avg_price REAL NOT NULL,
    realised_pnl REAL NOT NULL,
    last_updated TEXT NOT NULL,
    PRIMARY KEY (run_id, token_id)
);

CREATE TABLE IF NOT EXISTS cycle_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    cycle_number INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    universe_size INTEGER NOT NULL,
    snapshots_seen INTEGER NOT NULL,
    intents_generated INTEGER NOT NULL,
    intents_blocked INTEGER NOT NULL,
    fills_immediate INTEGER NOT NULL,
    fills_rested INTEGER NOT NULL,
    elapsed_seconds REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS cycle_metrics_run ON cycle_metrics(run_id, cycle_number);
"""
