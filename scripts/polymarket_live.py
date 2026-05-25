"""Run the live paper-trade loop.

Writes fills, equity snapshots, and positions to a SQLite database that the
Streamlit dashboard reads. Run-of-the-mill operation:

    PYTHONPATH=. python scripts/polymarket_live.py \\
        --db data/polymarket.sqlite \\
        --interval 60 --markets 30 --bankroll 10000

Stop with Ctrl+C (clean shutdown updates the runs table).
"""

from __future__ import annotations

import argparse
import logging
import sys

from quant_tool.polymarket import load_dotenv
from quant_tool.polymarket.live_runner import LiveRunner, LiveRunnerConfig
from quant_tool.polymarket.storage import default_db_path
from quant_tool.polymarket.strategy import STRATEGY_REGISTRY


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", default=str(default_db_path()),
                   help=f"SQLite path (default: {default_db_path()})")
    p.add_argument("--bankroll", type=float, default=10_000.0)
    p.add_argument("--interval", type=float, default=60.0,
                   help="Seconds between cycles (default: 60)")
    p.add_argument("--markets", type=int, default=30)
    p.add_argument("--strategies", type=str, default=",".join(STRATEGY_REGISTRY))
    p.add_argument("--max-per-market", type=float, default=0.02)
    p.add_argument("--max-total", type=float, default=0.50)
    p.add_argument("--trade-limit", type=int, default=50)
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv()

    names = tuple(n.strip() for n in args.strategies.split(",") if n.strip())
    unknown = [n for n in names if n not in STRATEGY_REGISTRY]
    if unknown:
        print(f"error: unknown strategies: {unknown}", file=sys.stderr)
        return 2

    config = LiveRunnerConfig(
        db_path=args.db, mode="paper", bankroll=args.bankroll,
        interval_seconds=args.interval, markets_per_cycle=args.markets,
        strategy_names=names, max_per_market=args.max_per_market,
        max_total=args.max_total, trade_limit=args.trade_limit,
    )
    runner = LiveRunner(config)
    runner.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
