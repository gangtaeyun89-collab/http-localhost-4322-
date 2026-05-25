"""Download SK Hynix (and optional context tickers) from Yahoo Finance.

Pure-Python with a graceful fallback: if ``yfinance`` is installed we use
it; otherwise we hit Yahoo's CSV endpoint directly.  Output is a Parquet
file (or CSV if pyarrow is unavailable) sitting next to the other
``download_*.py`` scripts in this repo.

Usage
-----
    python download_skhynix.py
    python download_skhynix.py --start 2010-01-01 --out data/skhynix.csv
"""

from __future__ import annotations

import argparse
import io
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


SKHYNIX = "000660.KS"
DEFAULT_CONTEXT = ["^KS11", "^SOX", "KRW=X"]   # KOSPI, PHLX semis, USDKRW


def fetch_yahoo(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch daily OHLCV from Yahoo Finance.

    Uses ``yfinance`` when present (cleanest path); otherwise falls back
    to Yahoo's public CSV download endpoint.
    """
    try:
        import yfinance as yf

        df = yf.download(
            symbol,
            start=start,
            end=end,
            auto_adjust=False,
            progress=False,
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except ImportError:
        return _fetch_yahoo_csv(symbol, start, end)


def _fetch_yahoo_csv(symbol: str, start: str, end: str) -> pd.DataFrame:
    p1 = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    p2 = int(datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v7/finance/download/{symbol}"
        f"?period1={p1}&period2={p2}&interval=1d&events=history"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
    df = pd.read_csv(io.StringIO(raw), parse_dates=["Date"]).set_index("Date")
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default=SKHYNIX)
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument(
        "--end", default=datetime.now().strftime("%Y-%m-%d")
    )
    parser.add_argument("--out", default="data/skhynix.parquet")
    parser.add_argument(
        "--with-context",
        action="store_true",
        help=f"Also fetch {DEFAULT_CONTEXT} as a panel.",
    )
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"Fetching {args.symbol}  {args.start} -> {args.end}")
    df = fetch_yahoo(args.symbol, args.start, args.end)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"

    if args.with_context:
        panel = {args.symbol: df["Close"]}
        for sym in DEFAULT_CONTEXT:
            try:
                time.sleep(0.3)
                ctx = fetch_yahoo(sym, args.start, args.end)
                ctx.index = pd.to_datetime(ctx.index).tz_localize(None)
                panel[sym] = ctx["Close"]
                print(f"  + {sym}: {len(ctx)} rows")
            except Exception as exc:
                print(f"  ! {sym} failed: {exc}", file=sys.stderr)
        df = pd.DataFrame(panel).dropna(how="all")

    _save(df, out)
    print(f"Wrote {len(df)} rows to {out}")
    return 0


def _save(df: pd.DataFrame, path: Path) -> None:
    if path.suffix == ".parquet":
        try:
            df.to_parquet(path)
            return
        except Exception:
            path = path.with_suffix(".csv")
            print(f"  parquet unavailable, writing {path} instead")
    df.to_csv(path)


if __name__ == "__main__":
    raise SystemExit(main())
