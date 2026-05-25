"""Live paper-trading runner that persists fills and equity to SQLite.

Unlike :class:`BakeOff` in :mod:`runner`, this one is designed to run for
hours or days as a daemon, with the dashboard polling the same database to
show live state. Two architectural differences:

* Every fill, equity snapshot, and position change is written through
  :class:`Storage` so the dashboard sees them immediately.
* The loop heart-beats the ``runs`` table each cycle so the dashboard can
  tell whether the runner is alive.

Live order placement (signing real Polymarket orders) is intentionally not
here -- that lives in the (still-to-be-built) ClobBroker for live mode only.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from quant_tool.polymarket.config import RiskLimits
from quant_tool.polymarket.data.clob_client import ClobClient
from quant_tool.polymarket.data.gamma_client import GammaClient
from quant_tool.polymarket.data.models import Market
from quant_tool.polymarket.execution.paper_broker import Fill, PaperBroker
from quant_tool.polymarket.risk.gate import RiskDecision, RiskGate
from quant_tool.polymarket.storage import Storage
from quant_tool.polymarket.strategy import STRATEGY_REGISTRY
from quant_tool.polymarket.strategy.base import Intent, MarketSnapshot, Side


log = logging.getLogger(__name__)


@dataclass
class LiveRunnerConfig:
    db_path: str
    mode: str = "paper"  # "live" reserved for the future ClobBroker
    bankroll: float = 10_000.0
    interval_seconds: float = 30.0
    markets_per_cycle: int = 30
    universe_limit: int = 200
    refresh_universe_every: int = 10
    strategy_names: tuple[str, ...] = tuple(STRATEGY_REGISTRY)
    strategy_overrides: dict[str, dict] = field(default_factory=dict)
    max_per_market: float = 0.02
    max_total: float = 0.50
    trade_limit: int = 50

    def __post_init__(self) -> None:
        if self.mode != "paper":
            raise ValueError("live mode requires ClobBroker; only 'paper' supported today")
        for name in self.strategy_names:
            if name not in STRATEGY_REGISTRY:
                raise ValueError(f"unknown strategy: {name}")


class LiveRunner:
    """Persistent paper-trade loop. Run via :meth:`run_forever`."""

    def __init__(self, config: LiveRunnerConfig,
                 *, storage: Storage | None = None,
                 clob: ClobClient | None = None,
                 gamma: GammaClient | None = None):
        self.config = config
        self.storage = storage or Storage(config.db_path)
        self.clob = clob or ClobClient()
        self.gamma = gamma or GammaClient()
        self.broker = PaperBroker(starting_cash=config.bankroll)
        self.risk = RiskGate(
            limits=RiskLimits(
                bankroll=config.bankroll,
                max_position_per_market=config.max_per_market,
                max_total_exposure=config.max_total,
            ),
            starting_equity=config.bankroll,
        )
        self.strategies = [
            STRATEGY_REGISTRY[n](**config.strategy_overrides.get(n, {}))
            for n in config.strategy_names
        ]
        self.run_id: int | None = None
        self._universe: tuple[Market, ...] = ()
        self._last_universe_refresh = -10**9
        self._mids: dict[str, float] = {}
        self._fill_strategy_by_token: dict[str, str] = {}
        self._stopping = False
        # Per-cycle counters reset at the start of each tick().
        self._cycle_intents = 0
        self._cycle_blocked = 0
        self._cycle_fills_immediate = 0
        self._cycle_fills_rested = 0

    # ----- lifecycle ----------------------------------------------------

    def start(self) -> int:
        """Open a new run row; return its id."""
        self.run_id = self.storage.start_run(
            mode=self.config.mode,
            bankroll=self.config.bankroll,
            config={
                "interval_seconds": self.config.interval_seconds,
                "markets_per_cycle": self.config.markets_per_cycle,
                "strategy_names": list(self.config.strategy_names),
                "strategy_overrides": self.config.strategy_overrides,
                "max_per_market": self.config.max_per_market,
                "max_total": self.config.max_total,
            },
            pid=os.getpid(),
        )
        log.info("started run id=%d (db=%s)", self.run_id, self.config.db_path)
        return self.run_id

    def stop(self) -> None:
        if self.run_id is not None:
            self.storage.end_run(self.run_id)
            log.info("ended run id=%d", self.run_id)

    def request_stop(self) -> None:
        self._stopping = True

    def run_forever(self, sleeper: Callable[[float], None] = time.sleep) -> None:
        if self.run_id is None:
            self.start()
        signal.signal(signal.SIGINT, lambda *_: self.request_stop())
        signal.signal(signal.SIGTERM, lambda *_: self.request_stop())
        try:
            cycles = 0
            while not self._stopping:
                t0 = time.monotonic()
                try:
                    self.tick(cycles)
                except Exception:  # noqa: BLE001
                    log.exception("tick failed; continuing")
                cycles += 1
                self.storage.heartbeat(self.run_id, cycles)  # type: ignore[arg-type]
                elapsed = time.monotonic() - t0
                sleep_for = max(0.0, self.config.interval_seconds - elapsed)
                if sleep_for > 0 and not self._stopping:
                    sleeper(sleep_for)
        finally:
            self.stop()

    # ----- one cycle ----------------------------------------------------

    def tick(self, cycle: int) -> None:
        cycle_start = time.monotonic()
        now = datetime.now(timezone.utc)
        # Reset per-cycle counters so the metric reflects only this cycle.
        self._cycle_intents = 0
        self._cycle_blocked = 0
        self._cycle_fills_immediate = 0
        self._cycle_fills_rested = 0

        self._refresh_universe_if_due(cycle)
        if not self._universe:
            log.warning("no universe yet; skipping cycle")
            return
        sample = self._universe[: self.config.markets_per_cycle]
        snapshots = self._fetch_snapshots(sample)
        for snap in snapshots:
            self._match_resting_against_trades(snap, now)
        for snap in snapshots:
            self._update_mids(snap)
            for strategy in self.strategies:
                for intent in strategy.on_snapshot(snap):
                    self._cycle_intents += 1
                    self._submit(intent, snap, now)
        self._mark_equity(now)
        # Persist the cycle metric so the live dashboard can chart it.
        if self.run_id is not None:
            self.storage.record_cycle_metric(
                self.run_id, cycle_number=cycle, timestamp=now,
                universe_size=len(self._universe),
                snapshots_seen=len(snapshots),
                intents_generated=self._cycle_intents,
                intents_blocked=self._cycle_blocked,
                fills_immediate=self._cycle_fills_immediate,
                fills_rested=self._cycle_fills_rested,
                elapsed_seconds=time.monotonic() - cycle_start,
            )
        log.info("[cycle %d] %d markets, %d intents (%d blocked), %d fills",
                 cycle, len(snapshots), self._cycle_intents, self._cycle_blocked,
                 self._cycle_fills_immediate + self._cycle_fills_rested)

    # ----- helpers ------------------------------------------------------

    def _refresh_universe_if_due(self, cycle: int) -> None:
        if cycle - self._last_universe_refresh < self.config.refresh_universe_every:
            return
        try:
            self._universe = self.gamma.active_markets(limit=self.config.universe_limit)
            self._last_universe_refresh = cycle
            log.info("[cycle %d] universe refreshed: %d markets", cycle, len(self._universe))
        except Exception:  # noqa: BLE001
            log.exception("universe refresh failed; reusing previous list")

    def _fetch_snapshots(self, markets) -> list[MarketSnapshot]:
        out = []
        for market in markets:
            try:
                yes_book = self.clob.orderbook(market.yes_token().token_id)
                no_book = self.clob.orderbook(market.no_token().token_id)
            except Exception:  # noqa: BLE001
                log.debug("book fetch failed for %s", market.condition_id, exc_info=True)
                continue
            trades = ()
            try:
                yt = self.clob.trades(market.yes_token().token_id, limit=self.config.trade_limit)
                nt = self.clob.trades(market.no_token().token_id, limit=self.config.trade_limit)
                trades = tuple(sorted(yt + nt, key=lambda t: t.timestamp))
            except Exception:  # noqa: BLE001
                log.debug("trade fetch failed for %s", market.condition_id, exc_info=True)
            out.append(MarketSnapshot(market=market, yes_book=yes_book,
                                       no_book=no_book, trades=trades))
        return out

    def _match_resting_against_trades(self, snap: MarketSnapshot, now: datetime) -> None:
        # If we have trade tape, use it; otherwise fall back to book-change matching.
        if snap.trades:
            for trade in snap.trades:
                for fill in self._consume_resting_for_trade(trade, now):
                    self._persist_fill(fill, snap.market.condition_id, fill_type="rested")
                    self._cycle_fills_rested += 1
        else:
            for book in (snap.yes_book, snap.no_book):
                for fill in self.broker.on_book(book, now=now):
                    self._persist_fill(fill, snap.market.condition_id, fill_type="rested")
                    self._cycle_fills_rested += 1

    def _consume_resting_for_trade(self, trade, now: datetime) -> list[Fill]:
        # Mirror of backtest._match_trade_to_resting -- one resting order credited per print.
        fills: list[Fill] = []
        to_remove: list[int] = []
        for order_id, resting in self.broker.open_orders.items():
            intent = resting.intent
            if intent.token_id != trade.token_id:
                continue
            crosses = (
                (intent.side is Side.BUY and trade.price <= intent.price)
                or (intent.side is Side.SELL and trade.price >= intent.price)
            )
            if not crosses:
                continue
            size = min(intent.size, trade.size)
            if size <= 0:
                continue
            fill = self.broker._record_fill(intent.strategy, intent.token_id, intent.side,
                                             intent.price, size, now)
            fills.append(fill)
            to_remove.append(order_id)
            break
        for order_id in to_remove:
            self.broker.open_orders.pop(order_id, None)
        return fills

    def _submit(self, intent: Intent, snap: MarketSnapshot, now: datetime) -> None:
        decision = self.risk.evaluate(intent, snap.market.condition_id, now)
        if decision is not RiskDecision.APPROVED:
            self._cycle_blocked += 1
            log.debug("blocked %s %s: %s", intent.strategy, snap.market.condition_id, decision.value)
            return
        book = (snap.yes_book if intent.token_id == snap.market.yes_token().token_id
                else snap.no_book)
        self._fill_strategy_by_token[intent.token_id] = intent.strategy
        fill = self.broker.submit(intent, book, now=now)
        if fill is not None:
            self.risk.record_fill(snap.market.condition_id, fill.side, fill.price * fill.size)
            self._persist_fill(fill, snap.market.condition_id, fill_type="immediate")
            self._cycle_fills_immediate += 1

    def _persist_fill(self, fill: Fill, condition_id: str, *, fill_type: str) -> None:
        assert self.run_id is not None
        self.storage.record_fill(
            self.run_id, timestamp=fill.timestamp, strategy=fill.strategy,
            token_id=fill.token_id, condition_id=condition_id, side=fill.side.value,
            price=fill.price, size=fill.size, post_only=(fill_type == "rested"),
            fill_type=fill_type,
        )
        pos = self.broker.positions.get(fill.token_id)
        if pos is not None:
            self.storage.upsert_position(
                self.run_id, token_id=fill.token_id, condition_id=condition_id,
                shares=pos.shares, avg_price=pos.avg_price, realised_pnl=pos.realised_pnl,
            )

    def _update_mids(self, snap: MarketSnapshot) -> None:
        for book in (snap.yes_book, snap.no_book):
            m = book.mid()
            if m is not None:
                self._mids[book.token_id] = m

    def _mark_equity(self, now: datetime) -> None:
        assert self.run_id is not None
        equity = self.broker.equity(self._mids)
        realised = self.broker.realised_pnl()
        unrealised = sum(
            (self._mids.get(t, p.avg_price) - p.avg_price) * p.shares
            for t, p in self.broker.positions.items()
            if p.shares != 0
        )
        self.risk.update_equity(equity, now=now)
        self.storage.record_equity(
            self.run_id, timestamp=now, cash=self.broker.cash, total_equity=equity,
            realised_pnl=realised, unrealised_pnl=unrealised,
        )
