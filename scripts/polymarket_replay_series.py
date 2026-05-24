"""Replay a JSONL capture series and run the full bake-off.

Unlike :mod:`polymarket_replay`, which simulates each snapshot in isolation,
this script feeds batches into the system in time order. Maker quotes from one
batch can rest and fill against later batches, which is the only way to get a
realistic read on the market-maker strategy's edge.

Per-strategy accounting is tracked via :class:`PaperBroker` so the final
report is grounded in actual simulated cash and positions, not just intent
counts.

Usage:
    python scripts/polymarket_replay_series.py capture.jsonl
    python scripts/polymarket_replay_series.py capture.jsonl --strategies arb_yes_no,market_maker
    python scripts/polymarket_replay_series.py capture.jsonl --equity-curve equity.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from quant_tool.polymarket.config import RiskLimits
from quant_tool.polymarket.data.snapshots import iter_batches
from quant_tool.polymarket.execution.paper_broker import PaperBroker
from quant_tool.polymarket.risk.gate import RiskDecision, RiskGate
from quant_tool.polymarket.strategy import STRATEGY_REGISTRY
from quant_tool.polymarket.strategy.base import MarketSnapshot, Side


@dataclass
class StratStats:
    name: str
    intents: int = 0
    blocked: int = 0
    immediate_fills: int = 0   # taker / crossing intents that filled on submit
    rested_fills: int = 0      # post-only intents that filled on a later batch
    notional_filled: float = 0.0
    realised_pnl: float = 0.0  # tracked at exit time; see _attribute_realised below


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("capture", type=Path)
    p.add_argument("--strategies", type=str, default=",".join(STRATEGY_REGISTRY))
    p.add_argument("--bankroll", type=float, default=10_000.0)
    p.add_argument("--max-per-market", type=float, default=0.02)
    p.add_argument("--max-total", type=float, default=0.50)
    p.add_argument("--equity-curve", type=Path, default=None,
                   help="If set, write per-cycle equity to this CSV.")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    names = [n.strip() for n in args.strategies.split(",") if n.strip()]
    unknown = [n for n in names if n not in STRATEGY_REGISTRY]
    if unknown:
        print(f"error: unknown strategies: {unknown}", file=sys.stderr)
        return 2

    strategies = {n: STRATEGY_REGISTRY[n]() for n in names}
    broker = PaperBroker(starting_cash=args.bankroll)
    risk = RiskGate(
        limits=RiskLimits(
            bankroll=args.bankroll,
            max_position_per_market=args.max_per_market,
            max_total_exposure=args.max_total,
        ),
        starting_equity=args.bankroll,
    )
    stats = {n: StratStats(name=n) for n in names}
    fill_strategy_by_token: dict[str, str] = {}  # so rested fills get attributed back

    equity_rows: list[tuple[str, float, float]] = []  # (captured_at, equity, realised)
    last_mids: dict[str, float] = {}
    batches_seen = 0
    cycle_open_intents = 0

    prints_seen = 0
    for batch in iter_batches(args.capture):
        batches_seen += 1
        # 1a. Match resting maker orders against trade prints (more accurate).
        #     Falls back to book-change matching when no trade tape is present.
        for snap in batch.snapshots:
            for trade in snap.trades:
                prints_seen += 1
                for fill in _match_trade_to_resting(broker, trade, batch.captured_at):
                    name = fill.strategy
                    stats[name].rested_fills += 1
                    stats[name].notional_filled += fill.price * fill.size
                    if args.verbose:
                        print(f"  [print fill] {name:<14} {fill.side.value:<4} "
                              f"@ {fill.price:.3f} x {fill.size:.1f}")
        # 1b. Book-change fallback for files without trade tape.
        for snap in batch.snapshots:
            if snap.trades:
                continue  # already handled via print matching
            for book in (snap.yes_book, snap.no_book):
                for fill in broker.on_book(book, now=batch.captured_at):
                    name = fill.strategy
                    stats[name].rested_fills += 1
                    stats[name].notional_filled += fill.price * fill.size
                    if args.verbose:
                        print(f"  [book fill ] {name:<14} {fill.side.value:<4} "
                              f"@ {fill.price:.3f} x {fill.size:.1f}")

        # 2. Run each strategy on each snapshot in this batch.
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
                    if fill is None:
                        cycle_open_intents += 1
                        continue
                    stats[name].immediate_fills += 1
                    stats[name].notional_filled += fill.price * fill.size
                    risk.record_fill(snap.market.condition_id, fill.side, fill.price * fill.size)
                    if args.verbose:
                        print(f"  [taker fill] {name:<14} {fill.side.value:<4} "
                              f"@ {fill.price:.3f} x {fill.size:.1f}")

        # 3. Mark-to-market + record equity for the curve.
        equity = broker.equity(last_mids)
        realised = broker.realised_pnl()
        risk.update_equity(equity, now=batch.captured_at)
        equity_rows.append((batch.captured_at.isoformat(), equity, realised))

    # ---- Attribution: split realised PnL by strategy ----
    # Positions track shares, not who placed them. We approximate by attributing
    # each position's realised PnL to the strategy that submitted the most recent
    # opening fill for its token. Good enough for a bake-off ranking; tighten
    # later if we want strict attribution.
    for token_id, pos in broker.positions.items():
        owner = fill_strategy_by_token.get(token_id)
        if owner and owner in stats:
            stats[owner].realised_pnl += pos.realised_pnl

    _print_report(batches_seen, broker, stats, equity_rows, cycle_open_intents, args, prints_seen)
    return 0


def _match_trade_to_resting(broker: PaperBroker, trade, now):
    """Credit resting maker orders when a print crosses them.

    A resting BUY at price p fills if any trade on the same token printed at
    price <= p (someone sold into our bid). Symmetric for SELL. We consume the
    intent's full size on the first match -- the trade tape doesn't tell us
    *whose* order filled, just that liquidity at that price was taken, so
    crediting a single resting order per print is a reasonable approximation.
    """
    from quant_tool.polymarket.execution.paper_broker import _RestingOrder  # local: private type

    fills = []
    to_remove = []
    for order_id, resting in broker.open_orders.items():
        intent = resting.intent
        if intent.token_id != trade.token_id:
            continue
        if intent.side is Side.BUY and trade.price <= intent.price:
            crosses = True
        elif intent.side is Side.SELL and trade.price >= intent.price:
            crosses = True
        else:
            crosses = False
        if not crosses:
            continue
        size = min(intent.size, trade.size)
        if size <= 0:
            continue
        # Build a synthetic fill record via the broker's bookkeeping helpers.
        fill = broker._record_fill(intent.strategy, intent.token_id, intent.side,
                                   intent.price, size, now)
        fills.append(fill)
        to_remove.append(order_id)
        break  # one resting order credited per print
    for order_id in to_remove:
        broker.open_orders.pop(order_id, None)
    return fills


def _update_mids(snap: MarketSnapshot, mids: dict[str, float]) -> None:
    for book in (snap.yes_book, snap.no_book):
        m = book.mid()
        if m is not None:
            mids[book.token_id] = m


def _print_report(batches: int, broker: PaperBroker, stats, equity_rows, open_intents, args, prints_seen: int = 0) -> None:
    print(f"\nReplayed {batches} batches; final cycle had {open_intents} open maker orders.")
    print(f"Trade prints in tape: {prints_seen}"
          + ("  (using trade-tape fill detection)" if prints_seen else "  (no trade tape -- using book-change fallback)"))
    if equity_rows:
        first_eq, last_eq = equity_rows[0][1], equity_rows[-1][1]
        peak_eq = max(r[1] for r in equity_rows)
        trough_after_peak = min((r[1] for r in equity_rows[equity_rows.index(max(equity_rows, key=lambda r: r[1])):]),
                                default=last_eq)
        max_dd = (peak_eq - trough_after_peak) / peak_eq if peak_eq > 0 else 0.0
        print(f"Equity: start ${first_eq:,.2f} -> end ${last_eq:,.2f}  "
              f"(peak ${peak_eq:,.2f}, max DD {max_dd*100:.2f}%)")
    print(f"Cash:               ${broker.cash:,.2f}")
    print(f"Open positions:     {sum(1 for p in broker.positions.values() if p.shares != 0)}")
    print(f"Realised PnL total: ${broker.realised_pnl():,.2f}")
    print()

    print("Per-strategy attribution:")
    header = f"  {'strategy':<14} {'intents':>8} {'blocked':>8} {'taker':>6} {'maker':>6} {'notional':>12} {'realised':>10}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for s in stats.values():
        print(f"  {s.name:<14} {s.intents:>8} {s.blocked:>8} {s.immediate_fills:>6} "
              f"{s.rested_fills:>6} ${s.notional_filled:>10,.0f} ${s.realised_pnl:>+8,.2f}")

    if args.equity_curve:
        with args.equity_curve.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["captured_at", "equity_usd", "realised_pnl_usd"])
            writer.writerows(equity_rows)
        print(f"\nWrote equity curve to {args.equity_curve}")


if __name__ == "__main__":
    sys.exit(main())
