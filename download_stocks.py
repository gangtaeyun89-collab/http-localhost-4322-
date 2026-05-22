#!/usr/bin/env python3
"""Download daily stock / ETF price history to CSV (via Stooq).

US stocks and ETFs are the building blocks of a long-term portfolio. This
pulls their free daily history from Stooq and writes CSVs in the format
``quant_tool.data.load_ohlcv`` reads, so they feed straight into the
allocation engine.

Run it on a machine with internet access. **No pip install needed** -- it uses
only the Python standard library.

Example
-------
    python download_stocks.py --symbols VTI VOO VXUS BND SGOV --out-dir market_data

A ticker that returns no data (wrong symbol, not on Stooq) is skipped with a
message. US tickers are looked up with a ``.us`` suffix automatically.
"""

from __future__ import annotations

import argparse
import csv
import io
import urllib.error
import urllib.request
from pathlib import Path

_STOOQ_URL = "https://stooq.com/q/d/l/?s={ticker}&i=d"
_OUT_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def fetch_stooq(symbol: str) -> list[list[str]]:
    """Fetch daily OHLCV rows for a US ticker from Stooq (header + data rows)."""
    ticker = symbol.lower()
    if not ticker.endswith(".us"):
        ticker += ".us"
    url = _STOOQ_URL.format(ticker=ticker)
    request = urllib.request.Request(url, headers={"User-Agent": "quant-tool"})
    with urllib.request.urlopen(request, timeout=60) as response:
        text = response.read().decode()
    return list(csv.reader(io.StringIO(text)))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--symbols", nargs="+", required=True, help="e.g. VTI VOO VXUS BND SGOV"
    )
    parser.add_argument("--out-dir", default="market_data")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for symbol in args.symbols:
        print(f"downloading {symbol} ...", flush=True)
        try:
            rows = fetch_stooq(symbol)
        except urllib.error.URLError as exc:
            print(f"  network error for {symbol}: {exc.reason}; skipping")
            continue
        # A valid response starts with a 'Date,Open,...' header row.
        if len(rows) < 2 or not rows[0] or rows[0][0].strip().lower() != "date":
            print(f"  no data for {symbol} -- check the ticker; skipping")
            continue

        path = out_dir / f"{symbol.upper()}.csv"
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(_OUT_COLUMNS)
            for row in rows[1:]:
                if len(row) >= 5:  # date,o,h,l,c[,volume]
                    writer.writerow(row[:6])
        print(f"  wrote {len(rows) - 1} rows -> {path}")


if __name__ == "__main__":
    main()
