"""Backtest engine: replay a JSONL capture series through the bake-off.

Extracted from :mod:`scripts.polymarket_replay_series` so the dashboard can
call the same code path. Returns a :class:`BacktestResult` instead of printing,
which lets callers render the data however they want (CLI tables, Streamlit
charts, JSON export, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from quant_tool.polymarket.config import RiskLimits
from quant_tool.polymarket.data.models import Trade
from quant_tool.polymarket.data.snapshots import SnapshotBatch, iter_batches
from quant_tool.polymarket.execution.paper_broker import Fill, PaperBroker, Position
from quant_tool.polymarket.risk.gate import RiskDecision, RiskGate
from quant_tool.polymarket.strategy import STRATEGY_REGISTRY
from quant_tool.polymarket.strategy.base import MarketSnapshot, Side


@dataclass
class StrategyStats:
    name: str
    intents: int = 0
    blocked: int = 0
    immediate_fills: int = 0
    rested_fills: int = 0
    notional_filled: float = 0.0
    realised_pnl: float = 0.0


@dataclass
class EquityPoint:
    timestamp: datetime
    equity: float
    realised_pnl: float


@dataclass
class BacktestResult:
    batches: int
    snapshots: int
    prints_seen: int
    open_orders_at_end: int

    starting_equity: float
    final_equity: float
    final_cash: float
    realised_pnl: float
    peak_equity: float
    max_drawdown: float  # fraction (0.05 = 5%)

    stats_by_strategy: dict[str, StrategyStats] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    positions: dict[str, Position] = field(default_factory=dict)


def run_backtest(
    capture_path: str | Path,
    strategy_names: Iterable[str] | None = None,
    *,
    bankroll: float = 10_000.0,
    max_per_market: float = 0.02,
    max_total: float = 0.50,
    strategy_overrides: dict[str, dict] | None = None,
) -> BacktestResult:
    """Replay a JSONL capture through strategies + broker; return structured results."""
    names = list(strategy_names) if strategy_names else list(STRATEGY_REGISTRY)
    overrides = strategy_overrides or {}
    strategies = {n: STRATEGY_REGISTRY[n](**overrides.get(n, {})) for n in names}

    broker = PaperBroker(starting_cash=bankroll)
    risk = RiskGate(
        limits=RiskLimits(
            bankroll=bankroll,
            max_position_per_market=max_per_market,
            max_total_exposure=max_total,
        ),
        starting_equity=bankroll,
    )
    stats = {n: StrategyStats(name=n) for n in names}
    fill_strategy_by_token: dict[str, str] = {}
    last_mids: dict[str, float] = {}
    equity_curve: list[EquityPoint] = []
    batches_seen = 0
    snapshots_seen = 0
    prints_seen = 0

    for batch in iter_batches(capture_path):
        batches_seen += 1
        snapshots_seen += len(batch.snapshots)

        # Print-based fill matching (preferred when trades are present)
        for snap in batch.snapshots:
            for trade in snap.trades:
                prints_seen += 1
                for fill in _match_trade_to_resting(broker, trade, batch.captured_at):
                    s = stats[fill.strategy]
                    s.rested_fills += 1
                    s.notional_filled += fill.price * fill.size

        # Book-change fallback for snapshots without trade tape
        for snap in batch.snapshots:
            if snap.trades:
                continue
            for book in (snap.yes_book, snap.no_book):
                for fill in broker.on_book(book, now=batch.captured_at):
                    s = stats[fill.strategy]
                    s.rested_fills += 1
                    s.notional_filled += fill.price * fill.size

        # Smart MMs cancel-and-replace each cycle to avoid stale-quote pickoffs.
        for name, strategy in strategies.items():
            if getattr(strategy, "cancel_before_quoting", False):
                broker.cancel_all_for_strategy(name)
        # Run strategies + risk-check + submit
        for snap in batch.snapshots:
            _update_mids(snap, last_mids)
            for name, strategy in strategies.items():
                intents = strategy.on_snapshot(snap)
                stats[name].intents += len(intents)
                for intent in intents:
                    decision = risk.evaluate(intent, snap.market.condition_id, batch.captured_at)
                    if decision is not RiskDecision.APPROVED:
                        stats[name].blocked += 1
                        continue
                    book = (snap.yes_book if intent.token_id == snap.market.yes_token().token_id
                            else snap.no_book)
                    fill_strategy_by_token[intent.token_id] = name
                    fill = broker.submit(intent, book, now=batch.captured_at)
                    if fill is not None:
                        s = stats[name]
                        s.immediate_fills += 1
                        s.notional_filled += fill.price * fill.size
                        risk.record_fill(snap.market.condition_id, fill.side, fill.price * fill.size)

        equity = broker.equity(last_mids)
        realised = broker.realised_pnl()
        risk.update_equity(equity, now=batch.captured_at)
        equity_curve.append(EquityPoint(batch.captured_at, equity, realised))

    # Attribute realised PnL by recording the strategy that last opened each token's position.
    for token_id, pos in broker.positions.items():
        owner = fill_strategy_by_token.get(token_id)
        if owner and owner in stats:
            stats[owner].realised_pnl += pos.realised_pnl

    peak = max((p.equity for p in equity_curve), default=bankroll)
    trough_after_peak = bankroll
    if equity_curve:
        peak_idx = max(range(len(equity_curve)), key=lambda i: equity_curve[i].equity)
        trough_after_peak = min((p.equity for p in equity_curve[peak_idx:]),
                                default=equity_curve[-1].equity)
    max_dd = (peak - trough_after_peak) / peak if peak > 0 else 0.0

    return BacktestResult(
        batches=batches_seen,
        snapshots=snapshots_seen,
        prints_seen=prints_seen,
        open_orders_at_end=len(broker.open_orders),
        starting_equity=bankroll,
        final_equity=equity_curve[-1].equity if equity_curve else bankroll,
        final_cash=broker.cash,
        realised_pnl=broker.realised_pnl(),
        peak_equity=peak,
        max_drawdown=max_dd,
        stats_by_strategy=stats,
        fills=list(broker.fills),
        equity_curve=equity_curve,
        positions=dict(broker.positions),
    )


def _match_trade_to_resting(broker: PaperBroker, trade: Trade, now: datetime) -> list[Fill]:
    """Credit at most one resting order per print at or through the trade price."""
    fills: list[Fill] = []
    to_remove: list[int] = []
    for order_id, resting in broker.open_orders.items():
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
        fill = broker._record_fill(intent.strategy, intent.token_id, intent.side,
                                   intent.price, size, now)
        fills.append(fill)
        to_remove.append(order_id)
        break
    for order_id in to_remove:
        broker.open_orders.pop(order_id, None)
    return fills


def _update_mids(snap: MarketSnapshot, mids: dict[str, float]) -> None:
    for book in (snap.yes_book, snap.no_book):
        m = book.mid()
        if m is not None:
            mids[book.token_id] = m
