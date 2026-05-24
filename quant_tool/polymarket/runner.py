"""Bake-off runner: wires data, strategies, risk, and broker into one loop.

The runner does **no** live trading. Live execution will plug a ``ClobBroker``
into this same loop once credentials are in place; the loop body is unchanged.

One process runs all enabled strategies in parallel against the same market
snapshots. Per-strategy PnL is attributed at fill time so the bake-off can rank
them without isolating them in separate processes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from quant_tool.polymarket.config import PolymarketConfig
from quant_tool.polymarket.data.clob_client import ClobClient
from quant_tool.polymarket.data.gamma_client import GammaClient
from quant_tool.polymarket.data.models import Market
from quant_tool.polymarket.execution.paper_broker import PaperBroker
from quant_tool.polymarket.risk.gate import RiskDecision, RiskGate
from quant_tool.polymarket.strategy import STRATEGY_REGISTRY
from quant_tool.polymarket.strategy.base import Intent, MarketSnapshot

log = logging.getLogger(__name__)


class _SupportsSnapshot(Protocol):
    name: str
    def on_snapshot(self, snapshot: MarketSnapshot) -> tuple[Intent, ...]: ...


@dataclass
class StrategyPnL:
    """Per-strategy attribution accumulated during the bake-off."""
    strategy: str
    realised: float = 0.0
    fills: int = 0
    blocked: int = 0


@dataclass
class BakeOff:
    config: PolymarketConfig
    clob: ClobClient
    gamma: GammaClient
    broker: PaperBroker
    risk: RiskGate
    strategies: list[_SupportsSnapshot] = field(default_factory=list)
    universe: tuple[Market, ...] = ()
    last_universe_refresh: datetime | None = None
    pnl: dict[str, StrategyPnL] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: PolymarketConfig) -> "BakeOff":
        broker = PaperBroker(starting_cash=config.risk.bankroll)
        risk = RiskGate(limits=config.risk, starting_equity=config.risk.bankroll)
        clob = ClobClient(base_url=config.clob_base_url)
        gamma = GammaClient(base_url=config.gamma_base_url)
        strategies: list[_SupportsSnapshot] = []
        for name in config.strategies:
            if name not in STRATEGY_REGISTRY:
                raise ValueError(f"unknown strategy: {name}")
            strategies.append(STRATEGY_REGISTRY[name]())
        pnl = {name: StrategyPnL(strategy=name) for name in config.strategies}
        return cls(config=config, clob=clob, gamma=gamma, broker=broker,
                   risk=risk, strategies=strategies, pnl=pnl)

    # ----- main loop ----------------------------------------------------

    def run_forever(self, sleeper=time.sleep) -> None:
        end = time.monotonic() + self.config.bake_off_days * 86_400
        while time.monotonic() < end:
            try:
                self.tick()
            except Exception:  # noqa: BLE001 -- a single-tick failure must not kill the bake-off
                log.exception("tick failed; continuing")
            sleeper(self.config.poll_interval_seconds)

    def tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self._refresh_universe(now)
        for market in self.universe:
            snapshot = self._snapshot(market)
            if snapshot is None:
                continue
            # Match resting maker orders against the new book before quoting again.
            for book in (snapshot.yes_book, snapshot.no_book):
                for fill in self.broker.on_book(book, now):
                    self._account_fill(market.condition_id, fill.strategy,
                                       fill.side, fill.price, fill.size)
            for strategy in self.strategies:
                for intent in strategy.on_snapshot(snapshot):
                    self._submit(intent, market, snapshot, now)
        self._mark_to_market(now)

    # ----- helpers ------------------------------------------------------

    def _refresh_universe(self, now: datetime) -> None:
        stale = (self.last_universe_refresh is None
                 or (now - self.last_universe_refresh).total_seconds()
                 > self.config.market_universe_refresh_minutes * 60)
        if stale:
            self.universe = self.gamma.active_markets()
            self.last_universe_refresh = now
            log.info("refreshed universe: %d markets", len(self.universe))

    def _snapshot(self, market: Market) -> MarketSnapshot | None:
        try:
            yes_book = self.clob.orderbook(market.yes_token().token_id)
            no_book = self.clob.orderbook(market.no_token().token_id)
        except Exception:  # noqa: BLE001
            log.debug("orderbook fetch failed for %s", market.condition_id, exc_info=True)
            return None
        return MarketSnapshot(market=market, yes_book=yes_book, no_book=no_book)

    def _submit(self, intent: Intent, market: Market,
                snapshot: MarketSnapshot, now: datetime) -> None:
        decision = self.risk.evaluate(intent, market.condition_id, now)
        if decision is not RiskDecision.APPROVED:
            self.pnl[intent.strategy].blocked += 1
            log.debug("blocked %s: %s", intent.strategy, decision.value)
            return
        book = snapshot.yes_book if intent.token_id == market.yes_token().token_id else snapshot.no_book
        fill = self.broker.submit(intent, book, now)
        if fill is not None:
            self._account_fill(market.condition_id, fill.strategy,
                               fill.side, fill.price, fill.size)

    def _account_fill(self, condition_id: str, strategy: str,
                      side, price: float, size: float) -> None:
        self.risk.record_fill(condition_id, side, price * size)
        bucket = self.pnl.setdefault(strategy, StrategyPnL(strategy=strategy))
        bucket.fills += 1
        bucket.realised = sum(pos.realised_pnl for pos in self.broker.positions.values())

    def _mark_to_market(self, now: datetime) -> None:
        marks = {}
        for market in self.universe:
            for token in market.tokens:
                # Reuse the most recent book if we have one; otherwise skip.
                pos = self.broker.positions.get(token.token_id)
                if pos is None or pos.shares == 0:
                    continue
                try:
                    mid = self.clob.midpoint(token.token_id)
                except Exception:  # noqa: BLE001
                    mid = None
                if mid is not None:
                    marks[token.token_id] = mid
        equity = self.broker.equity(marks)
        self.risk.update_equity(equity, now)
