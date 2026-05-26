#!/usr/bin/env python3
"""Download historical OHLCV from Interactive Brokers to CSV.

Run this on the machine where IB Gateway (or TWS) is running -- the script
connects to ``127.0.0.1:7497`` (Paper) by default. Output files match the
format ``quant_tool.data.load_ohlcv`` reads, so they drop straight into the
backtest and pair-discovery pipelines.

Examples
--------
A starter US-equity universe at daily resolution::

    python download_ibkr.py \\
        --universe sector_etfs megacap_tech \\
        --timeframe 1d --start 2020-01-01 --out-dir market_data/us_eq

Custom tickers, hourly bars (RTH only)::

    python download_ibkr.py \\
        --symbols AAPL MSFT GOOGL META AMZN \\
        --timeframe 1h --start 2024-01-01 --out-dir market_data/megacap_1h

Adjusted closes (split/dividend) for buy-and-hold style work::

    python download_ibkr.py --symbols SPY QQQ --timeframe 1d \\
        --start 2010-01-01 --what-to-show ADJUSTED_LAST
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from quant_tool.data import ibkr, universes


_UNIVERSE_NAMES = {
    "sector_etfs": universes.SECTOR_ETFS,
    "industry_etfs": universes.INDUSTRY_ETFS,
    "country_etfs": universes.COUNTRY_ETFS,
    "style_etfs": universes.STYLE_ETFS,
    "megacap_tech": universes.MEGACAP_TECH,
    "sp500_top_100": universes.SP500_TOP_100,
    "all_etfs": universes.all_etfs(),
    "all": universes.all_tickers(),
}


def _resolve_tickers(args) -> list[str]:
    tickers: list[str] = []
    if args.universe:
        for name in args.universe:
            if name not in _UNIVERSE_NAMES:
                raise SystemExit(
                    f"unknown universe {name!r}; choose from "
                    f"{sorted(_UNIVERSE_NAMES)}"
                )
            tickers.extend(_UNIVERSE_NAMES[name])
    if args.symbols:
        tickers.extend(args.symbols)
    # de-duplicate while preserving order
    seen: dict[str, None] = {}
    for t in tickers:
        seen[t] = None
    return list(seen.keys())


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--symbols", nargs="+", help="explicit ticker list, e.g. AAPL MSFT GOOGL"
    )
    parser.add_argument(
        "--universe",
        nargs="+",
        choices=sorted(_UNIVERSE_NAMES),
        help="one or more named universes from quant_tool.data.universes",
    )
    parser.add_argument("--timeframe", default="1d", help="e.g. 1d, 1h, 5m, 1m")
    parser.add_argument(
        "--start", required=True, help="history start, ISO date e.g. 2020-01-01"
    )
    parser.add_argument(
        "--end", default=None, help="history end, ISO date (default: now)"
    )
    parser.add_argument(
        "--what-to-show",
        default="TRADES",
        choices=["TRADES", "MIDPOINT", "BID", "ASK", "ADJUSTED_LAST"],
        help="IBKR price type; ADJUSTED_LAST gives split/dividend-adjusted closes",
    )
    parser.add_argument(
        "--use-rth",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="restrict to Regular Trading Hours (default: True)",
    )
    parser.add_argument("--host", default=ibkr.DEFAULT_HOST)
    parser.add_argument(
        "--port",
        type=int,
        default=ibkr.DEFAULT_PAPER_PORT,
        help=f"gateway port; {ibkr.DEFAULT_PAPER_PORT}=paper, "
        f"{ibkr.DEFAULT_LIVE_PORT}=live",
    )
    parser.add_argument("--client-id", type=int, default=11)
    parser.add_argument("--out-dir", default="market_data/ibkr")
    parser.add_argument(
        "--symbol-pause",
        type=float,
        default=1.5,
        help="seconds to sleep between symbols to respect IBKR pacing",
    )
    args = parser.parse_args()

    tickers = _resolve_tickers(args)
    if not tickers:
        raise SystemExit("supply --symbols or --universe")

    print(
        f"connecting to IBKR at {args.host}:{args.port} (client {args.client_id}) ..."
    )
    ib = ibkr.connect(host=args.host, port=args.port, client_id=args.client_id)
    print(f"  connected, accounts={ib.managedAccounts()}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ok, failed = 0, []
    try:
        for i, symbol in enumerate(tickers, 1):
            print(f"[{i}/{len(tickers)}] {symbol} ...", flush=True)
            try:
                df = ibkr.fetch_historical(
                    ib,
                    symbol=symbol,
                    timeframe=args.timeframe,
                    start=args.start,
                    end=args.end,
                    what_to_show=args.what_to_show,
                    use_rth=args.use_rth,
                )
            except Exception as exc:  # noqa: BLE001 - report and continue
                print(f"  ERROR {symbol}: {exc}")
                failed.append(symbol)
                continue
            if df.empty:
                print(f"  no data for {symbol}")
                failed.append(symbol)
                continue
            path = out_dir / f"{symbol.replace('.', '-')}.csv"
            ibkr.save_ohlcv(df, path)
            print(f"  wrote {len(df)} bars -> {path}")
            ok += 1
            time.sleep(args.symbol_pause)
    finally:
        ib.disconnect()

    print(f"\ndone. ok={ok}, failed={len(failed)}")
    if failed:
        print("failed:", " ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
