"""Recurring Polymarket snapshot capture.

Runs in the foreground (or under nohup/tmux), polls Gamma for the active
market universe, fetches YES/NO orderbooks for the top ``--markets``, and
appends one JSONL line per cycle to ``--output``. Designed to run for hours
to a day on a laptop so we have a real time-series for backtesting.

Usage examples:
    # 3 hours, snapshot every 2 minutes, 25 markets per cycle
    python scripts/polymarket_capture.py --output capture.jsonl \\
        --interval 120 --duration 10800 --markets 25

    # Until Ctrl+C, snapshot every minute
    python scripts/polymarket_capture.py --output capture.jsonl --interval 60

The output file is append-only and crash-safe: each cycle is a complete JSON
line, so killing the process at any moment leaves a readable JSONL file.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from quant_tool.polymarket import load_dotenv
from quant_tool.polymarket.data.clob_client import ClobClient
from quant_tool.polymarket.data.gamma_client import GammaClient
from quant_tool.polymarket.data.snapshots import append_batch
from quant_tool.polymarket.strategy.base import MarketSnapshot


log = logging.getLogger("polymarket_capture")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--output", type=Path, required=True,
                   help="Append-mode JSONL file. Created if missing.")
    p.add_argument("--interval", type=float, default=120.0,
                   help="Seconds between capture cycles (default: 120)")
    p.add_argument("--duration", type=float, default=None,
                   help="Stop after this many seconds (default: run until Ctrl+C)")
    p.add_argument("--markets", type=int, default=25,
                   help="Number of top markets to fetch each cycle (default: 25)")
    p.add_argument("--universe-limit", type=int, default=200,
                   help="Pull this many active markets from Gamma each cycle "
                        "before truncating to --markets (default: 200)")
    p.add_argument("--refresh-universe-every", type=int, default=10,
                   help="Re-fetch the active-market list every N cycles "
                        "(default: 10; intermediate cycles reuse it)")
    p.add_argument("--trade-limit", type=int, default=50,
                   help="Recent trades to fetch per token per cycle (default: 50)")
    p.add_argument("--no-trades", action="store_true",
                   help="Skip trade-tape fetching (faster, books only)")
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()

    clob = ClobClient()
    gamma = GammaClient()

    stop_at = (time.monotonic() + args.duration) if args.duration else None
    cycles = 0
    fills_written = 0
    book_failures = 0
    universe = ()
    last_universe_refresh = -10**9  # force initial refresh

    # Graceful Ctrl+C: finish current cycle, then exit.
    stopping = {"flag": False}

    def _on_sigint(signum, frame):  # noqa: ARG001
        log.info("stop requested -- will exit after current cycle")
        stopping["flag"] = True

    signal.signal(signal.SIGINT, _on_sigint)

    log.info("output=%s interval=%.1fs markets=%d duration=%s",
             args.output, args.interval, args.markets,
             f"{args.duration}s" if args.duration else "until-Ctrl+C")

    while True:
        if stopping["flag"]:
            break
        if stop_at is not None and time.monotonic() >= stop_at:
            log.info("duration reached; exiting")
            break

        cycle_start = time.monotonic()
        cycles += 1

        # Refresh universe periodically -- expensive call, snapshots are cheap.
        if cycles - last_universe_refresh >= args.refresh_universe_every:
            try:
                universe = gamma.active_markets(limit=args.universe_limit)
                last_universe_refresh = cycles
                log.info("[cycle %d] refreshed universe: %d markets", cycles, len(universe))
            except Exception:  # noqa: BLE001
                log.exception("[cycle %d] failed to refresh universe; reusing previous", cycles)

        if not universe:
            log.warning("[cycle %d] no universe yet; sleeping and retrying", cycles)
            time.sleep(min(args.interval, 30))
            continue

        sample = universe[: args.markets]
        captured = []
        for market in sample:
            try:
                yes_book = clob.orderbook(market.yes_token().token_id)
                no_book = clob.orderbook(market.no_token().token_id)
            except Exception as exc:  # noqa: BLE001
                book_failures += 1
                log.debug("book fetch failed for %s: %s", market.condition_id, exc)
                continue
            trades = ()
            if not args.no_trades:
                try:
                    yes_trades = clob.trades(market.yes_token().token_id, limit=args.trade_limit)
                    no_trades = clob.trades(market.no_token().token_id, limit=args.trade_limit)
                    trades = tuple(sorted(yes_trades + no_trades, key=lambda t: t.timestamp))
                except Exception as exc:  # noqa: BLE001
                    log.debug("trade fetch failed for %s: %s", market.condition_id, exc)
            captured.append(MarketSnapshot(market=market, yes_book=yes_book,
                                           no_book=no_book, trades=trades))

        if not captured:
            log.warning("[cycle %d] no books retrieved; skipping write", cycles)
        else:
            append_batch(args.output, captured,
                         captured_at=datetime.now(timezone.utc),
                         universe_size=len(universe))
            fills_written += len(captured)
            elapsed = time.monotonic() - cycle_start
            log.info("[cycle %d] wrote %d snapshots in %.1fs (total written: %d, book failures: %d)",
                     cycles, len(captured), elapsed, fills_written, book_failures)

        # Sleep the remaining time so cycles stay on a regular cadence.
        next_at = cycle_start + args.interval
        sleep_for = max(0.0, next_at - time.monotonic())
        if sleep_for and not stopping["flag"]:
            time.sleep(sleep_for)

    print(f"\nWrote {cycles} cycles ({fills_written} snapshots, {book_failures} book failures) to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
