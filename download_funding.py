#!/usr/bin/env python3
"""Download perpetual-futures funding-rate history to CSV.

The funding-rate carry trade -- hold spot, short the perpetual, collect the
periodic funding payment -- is driven by *funding rates*, not candles. This
script pulls a contract's full funding-rate history via ccxt and writes one
CSV per symbol (``timestamp, funding_rate``).

Run it on a machine with internet access.

Example
-------
    python download_funding.py \\
        --symbols BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT \\
        --start 2025-01-01 --exchange binance --out-dir funding_data

The ``BASE/QUOTE:QUOTE`` form is ccxt's symbol for a linear perpetual. Funding
is typically paid every 8 hours, so expect ~3 records per day.
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path


def download_funding(exchange, symbol, since_ms, page_limit):
    """Page through a contract's funding-rate history from ``since_ms`` to now."""
    rows: list[dict] = []
    cursor = since_ms
    while True:
        batch = exchange.fetch_funding_rate_history(
            symbol, since=cursor, limit=page_limit
        )
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1]["timestamp"] + 1
        if len(batch) < page_limit:
            break
        time.sleep(exchange.rateLimit / 1000.0)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--symbols", nargs="+", required=True,
        help="perpetual symbols, e.g. BTC/USDT:USDT ETH/USDT:USDT",
    )
    parser.add_argument("--start", required=True, help="ISO date, e.g. 2025-01-01")
    parser.add_argument("--exchange", default="binance", help="any ccxt exchange id")
    parser.add_argument("--out-dir", default="funding_data")
    parser.add_argument("--page-limit", type=int, default=1000)
    args = parser.parse_args()

    try:
        import ccxt
    except ImportError:
        raise SystemExit("this script requires ccxt:  pip install ccxt")

    exchange = getattr(ccxt, args.exchange)(
        {"enableRateLimit": True, "options": {"defaultType": "swap"}}
    )
    since_ms = exchange.parse8601(f"{args.start}T00:00:00Z")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for symbol in args.symbols:
        print(f"downloading funding history for {symbol} ...", flush=True)
        try:
            rows = download_funding(exchange, symbol, since_ms, args.page_limit)
        except Exception as exc:  # bad symbol, exchange quirk -- keep going
            print(f"  failed for {symbol}: {exc}; skipping")
            continue
        if not rows:
            print(f"  no funding data for {symbol} -- skipping")
            continue
        safe = symbol.replace("/", "-").replace(":", "_")
        path = out_dir / f"{safe}.csv"
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "funding_rate"])
            for record in rows:
                writer.writerow([int(record["timestamp"]), record["fundingRate"]])
        print(f"  wrote {len(rows)} funding records -> {path}")


if __name__ == "__main__":
    main()
