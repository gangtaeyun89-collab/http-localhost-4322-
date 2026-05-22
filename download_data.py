#!/usr/bin/env python3
"""Download historical OHLCV candles to CSV for real-data backtesting.

Run this on a machine with internet access -- the research/backtest
environment is often network-isolated. It pages through an exchange's full
history and writes one CSV per symbol in the exact format
``quant_tool.data.load_ohlcv`` reads, so the files drop straight into
``run_backtest.py --base-csv/--quote-csv`` or a universe for ``run_portfolio``.

Example
-------
Roughly a year of hourly candles for a starter universe::

    python download_data.py \\
        --symbols BTC/USDT ETH/USDT SOL/USDT BNB/USDT AVAX/USDT \\
                  ADA/USDT LINK/USDT DOT/USDT ATOM/USDT MATIC/USDT \\
        --timeframe 1h --start 2025-01-01 --out-dir market_data

Then hand the ``market_data/*.csv`` files to the toolkit.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def download_symbol(exchange, symbol, timeframe, since_ms, page_limit):
    """Page through an exchange's OHLCV history from ``since_ms`` to now."""
    rows: list[list] = []
    cursor = since_ms
    while True:
        batch = exchange.fetch_ohlcv(
            symbol, timeframe=timeframe, since=cursor, limit=page_limit
        )
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0] + 1  # one millisecond past the last candle
        if len(batch) < page_limit:
            break
        time.sleep(exchange.rateLimit / 1000.0)  # respect the rate limit
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--symbols", nargs="+", required=True, help="e.g. BTC/USDT ETH/USDT"
    )
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument(
        "--start", required=True, help="history start, ISO date e.g. 2025-01-01"
    )
    parser.add_argument("--exchange", default="binance", help="any ccxt exchange id")
    parser.add_argument("--out-dir", default="market_data")
    parser.add_argument("--page-limit", type=int, default=1000)
    args = parser.parse_args()

    try:
        import ccxt
    except ImportError:
        raise SystemExit("this script requires ccxt:  pip install ccxt")

    exchange = getattr(ccxt, args.exchange)({"enableRateLimit": True})
    since_ms = exchange.parse8601(f"{args.start}T00:00:00Z")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for symbol in args.symbols:
        print(f"downloading {symbol} ...", flush=True)
        rows = download_symbol(
            exchange, symbol, args.timeframe, since_ms, args.page_limit
        )
        if not rows:
            print(f"  no data returned for {symbol} -- skipping")
            continue
        frame = pd.DataFrame(rows, columns=_COLUMNS)
        frame = frame.drop_duplicates(subset="timestamp").sort_values("timestamp")
        path = out_dir / f"{symbol.replace('/', '-')}.csv"
        frame.to_csv(path, index=False)
        print(f"  wrote {len(frame)} candles -> {path}")


if __name__ == "__main__":
    main()
