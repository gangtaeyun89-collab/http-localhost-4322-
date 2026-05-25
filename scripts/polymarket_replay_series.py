"""Replay a JSONL capture series and print bake-off results.

Thin wrapper around :func:`quant_tool.polymarket.backtest.run_backtest`. The
dashboard calls the same function and renders the same result object as charts.

Usage:
    python scripts/polymarket_replay_series.py capture.jsonl
    python scripts/polymarket_replay_series.py capture.jsonl --strategies arb_yes_no,market_maker
    python scripts/polymarket_replay_series.py capture.jsonl --equity-curve equity.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from quant_tool.polymarket.backtest import run_backtest
from quant_tool.polymarket.strategy import STRATEGY_REGISTRY


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("capture", type=Path)
    p.add_argument("--strategies", type=str, default=",".join(STRATEGY_REGISTRY))
    p.add_argument("--bankroll", type=float, default=10_000.0)
    p.add_argument("--max-per-market", type=float, default=0.02)
    p.add_argument("--max-total", type=float, default=0.50)
    p.add_argument("--equity-curve", type=Path, default=None,
                   help="If set, write per-cycle equity to this CSV.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    names = [n.strip() for n in args.strategies.split(",") if n.strip()]
    unknown = [n for n in names if n not in STRATEGY_REGISTRY]
    if unknown:
        print(f"error: unknown strategies: {unknown}", file=sys.stderr)
        return 2

    result = run_backtest(
        args.capture,
        strategy_names=names,
        bankroll=args.bankroll,
        max_per_market=args.max_per_market,
        max_total=args.max_total,
    )

    print(f"\nReplayed {result.batches} batches ({result.snapshots} snapshots); "
          f"final cycle had {result.open_orders_at_end} open maker orders.")
    print(f"Trade prints in tape: {result.prints_seen}"
          + ("  (using trade-tape fill detection)" if result.prints_seen
             else "  (no trade tape -- using book-change fallback)"))
    print(f"Equity: start ${result.starting_equity:,.2f} -> end ${result.final_equity:,.2f}  "
          f"(peak ${result.peak_equity:,.2f}, max DD {result.max_drawdown*100:.2f}%)")
    print(f"Cash:               ${result.final_cash:,.2f}")
    print(f"Open positions:     {sum(1 for p in result.positions.values() if p.shares != 0)}")
    print(f"Realised PnL total: ${result.realised_pnl:,.2f}")
    print()

    print("Per-strategy attribution:")
    header = f"  {'strategy':<14} {'intents':>8} {'blocked':>8} {'taker':>6} {'maker':>6} {'notional':>12} {'realised':>10}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for s in result.stats_by_strategy.values():
        print(f"  {s.name:<14} {s.intents:>8} {s.blocked:>8} {s.immediate_fills:>6} "
              f"{s.rested_fills:>6} ${s.notional_filled:>10,.0f} ${s.realised_pnl:>+8,.2f}")

    if args.equity_curve:
        with args.equity_curve.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["captured_at", "equity_usd", "realised_pnl_usd"])
            for pt in result.equity_curve:
                writer.writerow([pt.timestamp.isoformat(), pt.equity, pt.realised_pnl])
        print(f"\nWrote equity curve to {args.equity_curve}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
