#!/usr/bin/env python3
"""Download token price history from CoinGecko to CSV.

For tokens that don't trade on major centralised exchanges -- Solana liquid-
staking tokens (mSOL, jitoSOL, ...), wrapped assets, long-tail tokens -- the
ccxt-based ``download_data.py`` has no data. This script pulls their price
history from CoinGecko's public API instead, writing CSVs in the exact format
``quant_tool.data.load_ohlcv`` reads.

Run it on a machine with internet access. **No pip install needed** -- it uses
only the Python standard library.

Example
-------
    python download_coingecko.py \\
        --coins solana msol jito-staked-sol blazestake-staked-sol \\
        --days 90 --out-dir market_data

Notes
-----
* CoinGecko's free tier returns ~hourly data for a 2-90 day window; above 90
  days it becomes daily. For a fast-reverting LST/SOL spread, 90 days hourly
  (~2000 bars) is plenty.
* A coin's id is the slug in its CoinGecko URL (coingecko.com/en/coins/<id>).
  Verify the ids -- a wrong one is skipped with an HTTP 404.
* If you hit rate limits, pass a free CoinGecko demo key via ``--api-key``.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

_BASE = "https://api.coingecko.com/api/v3"


def fetch_prices(coin_id: str, vs_currency: str, days: str, api_key: str | None):
    """Fetch ``[timestamp_ms, price]`` points for one coin from CoinGecko."""
    url = (
        f"{_BASE}/coins/{coin_id}/market_chart"
        f"?vs_currency={vs_currency}&days={days}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "quant-tool"})
    if api_key:
        request.add_header("x-cg-demo-api-key", api_key)
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode())
    return payload.get("prices", [])


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--coins", nargs="+", required=True,
        help="CoinGecko coin ids, e.g. solana msol jito-staked-sol",
    )
    parser.add_argument("--days", default="90", help="days of history (2-90 = hourly)")
    parser.add_argument("--vs", default="usd", help="quote currency")
    parser.add_argument("--out-dir", default="market_data")
    parser.add_argument("--api-key", default=None, help="optional CoinGecko demo key")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for coin_id in args.coins:
        print(f"downloading {coin_id} ...", flush=True)
        try:
            prices = fetch_prices(coin_id, args.vs, args.days, args.api_key)
        except urllib.error.HTTPError as exc:
            print(f"  HTTP {exc.code} for '{coin_id}' -- check the coin id; skipping")
            continue
        except urllib.error.URLError as exc:
            print(f"  network error for '{coin_id}': {exc.reason}; skipping")
            continue
        if not prices:
            print(f"  no data returned for '{coin_id}'; skipping")
            continue

        path = out_dir / f"{coin_id}.csv"
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "close"])
            for timestamp_ms, price in prices:
                writer.writerow([int(timestamp_ms), price])
        print(f"  wrote {len(prices)} points -> {path}")
        time.sleep(2.5)  # stay within the free-tier rate limit


if __name__ == "__main__":
    main()
