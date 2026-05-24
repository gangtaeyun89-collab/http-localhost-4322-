"""Replay a captured snapshot file through the strategies and paper broker.

Loads the JSON produced by ``polymarket_smoke.py --save``, runs every requested
strategy on each snapshot, simulates fills against the captured book, and
prints per-strategy attribution. Strategy parameters can be overridden via
CLI flags so we can sweep without re-fetching live data.

Usage:
    python scripts/polymarket_replay.py snapshot.json
    python scripts/polymarket_replay.py snapshot.json --strategies arb_yes_no --verbose
    python scripts/polymarket_replay.py snapshot.json --mm-quote-size 50 --arb-min-edge 0.003
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from quant_tool.polymarket.data.snapshots import load_snapshots
from quant_tool.polymarket.execution.paper_broker import PaperBroker
from quant_tool.polymarket.strategy import STRATEGY_REGISTRY
from quant_tool.polymarket.strategy.arb_yes_no import YesNoArb
from quant_tool.polymarket.strategy.base import Intent, MarketSnapshot, Side
from quant_tool.polymarket.strategy.market_maker import MarketMaker
from quant_tool.polymarket.strategy.signal_model import SignalModel


@dataclass
class StrategyStats:
    name: str
    intents: int = 0
    filled: int = 0
    notional_filled: float = 0.0
    immediate_pnl: float = 0.0  # fill price vs same-snapshot mid

    def line(self) -> str:
        fill_rate = (self.filled / self.intents * 100) if self.intents else 0.0
        return (f"  {self.name:<15} {self.intents:>5} intents, "
                f"{self.filled:>4} filled ({fill_rate:5.1f}%), "
                f"notional ${self.notional_filled:>9,.0f}, "
                f"immediate PnL ${self.immediate_pnl:>+8,.2f}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("snapshot", type=Path, help="Path to a JSON snapshot file from --save")
    p.add_argument("--strategies", type=str, default=",".join(STRATEGY_REGISTRY))
    p.add_argument("--bankroll", type=float, default=10_000.0)
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Print every intent and its fill outcome")

    # Parameter overrides -- one per tunable knob.
    p.add_argument("--mm-quote-size", type=float, default=None)
    p.add_argument("--mm-min-spread-ticks", type=int, default=None)
    p.add_argument("--arb-min-edge", type=float, default=None)
    p.add_argument("--arb-max-clip", type=float, default=None)
    p.add_argument("--signal-ema-alpha", type=float, default=None)
    p.add_argument("--signal-momentum", type=float, default=None)
    return p.parse_args()


def build_strategies(args: argparse.Namespace, names: list[str]):
    """Instantiate strategies, applying CLI overrides where given."""
    instances = []
    for name in names:
        if name == "market_maker":
            kwargs = {}
            if args.mm_quote_size is not None:
                kwargs["quote_size"] = args.mm_quote_size
            if args.mm_min_spread_ticks is not None:
                kwargs["min_spread_ticks"] = args.mm_min_spread_ticks
            instances.append(MarketMaker(**kwargs))
        elif name == "arb_yes_no":
            kwargs = {}
            if args.arb_min_edge is not None:
                kwargs["min_edge"] = args.arb_min_edge
            if args.arb_max_clip is not None:
                kwargs["max_clip_shares"] = args.arb_max_clip
            instances.append(YesNoArb(**kwargs))
        elif name == "signal_model":
            kwargs = {}
            if args.signal_ema_alpha is not None:
                kwargs["ema_alpha"] = args.signal_ema_alpha
            if args.signal_momentum is not None:
                kwargs["momentum_threshold"] = args.signal_momentum
            instances.append(SignalModel(**kwargs))
        elif name in STRATEGY_REGISTRY:
            instances.append(STRATEGY_REGISTRY[name]())
        else:
            print(f"error: unknown strategy {name!r}", file=sys.stderr)
            sys.exit(2)
    return instances


def main() -> int:
    args = parse_args()
    snap_file = load_snapshots(args.snapshot)
    print(f"Loaded {len(snap_file.snapshots)} snapshots captured at {snap_file.captured_at}")
    print(f"Original universe size: {snap_file.universe_size}\n")

    names = [n.strip() for n in args.strategies.split(",") if n.strip()]
    strategies = build_strategies(args, names)
    broker = PaperBroker(starting_cash=args.bankroll)
    stats: dict[str, StrategyStats] = {n: StrategyStats(name=n) for n in names}

    book_quality_warnings = _book_quality(snap_file.snapshots)
    if book_quality_warnings:
        print("Book-quality notes:")
        for w in book_quality_warnings:
            print(f"  - {w}")
        print()

    for snap in snap_file.snapshots:
        for strategy in strategies:
            intents = strategy.on_snapshot(snap)
            stat = stats[strategy.name]
            stat.intents += len(intents)
            for intent in intents:
                fill = _simulate_intent(broker, intent, snap)
                if fill is None:
                    if args.verbose:
                        print(f"  [no fill] {_describe_intent(intent, snap)}")
                    continue
                stat.filled += 1
                stat.notional_filled += fill.price * fill.size
                mid = _mid_for(intent.token_id, snap)
                if mid is not None:
                    sign = 1 if intent.side is Side.BUY else -1
                    stat.immediate_pnl += sign * (mid - fill.price) * fill.size
                if args.verbose:
                    print(f"  [fill ]   {_describe_intent(intent, snap)}"
                          f" -> {fill.price:.3f} x {fill.size:.1f}")

    print("Per-strategy results:")
    for stat in stats.values():
        print(stat.line())

    print(f"\nBroker cash after replay:    ${broker.cash:,.2f}")
    print(f"Open positions:              {sum(1 for p in broker.positions.values() if p.shares != 0)}")
    print(f"Realised PnL across markets: ${broker.realised_pnl():,.2f}")
    return 0


def _simulate_intent(broker: PaperBroker, intent: Intent, snap: MarketSnapshot):
    book = snap.yes_book if intent.token_id == snap.market.yes_token().token_id else snap.no_book
    return broker.submit(intent, book)


def _mid_for(token_id: str, snap: MarketSnapshot) -> float | None:
    book = snap.yes_book if token_id == snap.market.yes_token().token_id else snap.no_book
    return book.mid()


def _describe_intent(intent: Intent, snap: MarketSnapshot) -> str:
    side = intent.side.value
    outcome = "YES" if intent.token_id == snap.market.yes_token().token_id else "NO"
    q = snap.market.question[:40]
    return f"{intent.strategy:<15} {side:<4} {outcome} @ {intent.price:.3f} x {intent.size:>5.1f} ({q!r})"


def _book_quality(snapshots) -> list[str]:
    """Quick sanity checks on the captured books for the analyst's benefit."""
    warnings = []
    empty_books = sum(
        1 for s in snapshots
        if not (s.yes_book.bids and s.yes_book.asks and s.no_book.bids and s.no_book.asks)
    )
    if empty_books:
        warnings.append(f"{empty_books}/{len(snapshots)} markets have one or more empty book sides")
    yes_no_sums = []
    for s in snapshots:
        yb = s.yes_book.best_bid()
        nb = s.no_book.best_bid()
        if yb and nb:
            yes_no_sums.append(yb.price + nb.price)
    if yes_no_sums:
        avg = sum(yes_no_sums) / len(yes_no_sums)
        warnings.append(f"mean YES_bid + NO_bid across markets: {avg:.4f} (1.0 = no arb)")
    arb_count = sum(1 for v in yes_no_sums if v > 1.001)
    if arb_count:
        warnings.append(f"{arb_count} markets show bid-side YES+NO sum > 1.001 (potential arb)")
    return warnings


if __name__ == "__main__":
    raise SystemExit(main())
