#!/usr/bin/env python3
"""Generate the weekly portfolio report.

Reads your current holdings, compares them to the three target sleeves, and
prints a report: per-sleeve drift, recommended rebalancing trades, and risk
flags. You read it and decide -- nothing trades automatically (recommend mode).

Holdings file (CSV) -- one row per (sleeve, asset) you currently hold; use
``CASH`` for un-invested money:

    sleeve,asset,value
    Growth,VTI,8000
    Growth,CASH,2000
    Balanced,SGOV,5000
    Reserve,CASH,3000

Example
-------
    python run_report.py --holdings holdings.csv --data-dir market_data
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from quant_tool.allocation.report import Sleeve, build_report
from quant_tool.data.ingestion import load_ohlcv
from quant_tool.monitoring import get_logger

log = get_logger("report")

# The three sleeves, as backtested. Edit the weights to suit your family.
SLEEVES = [
    Sleeve(
        "Growth",
        pd.Series({"VTI": 0.80, "VXUS": 0.15, "BND": 0.05}),
        note="10+ year money",
    ),
    Sleeve(
        "Balanced",
        pd.Series({"VTI": 0.45, "VXUS": 0.15, "BND": 0.40}),
        note="3-10 year money",
    ),
    Sleeve(
        "Reserve",
        pd.Series({"SGOV": 1.00}),
        note="under 3 years -- capital preservation",
    ),
]


def _load_holdings(path: str) -> dict[str, pd.Series]:
    """Read the holdings CSV into a sleeve -> (asset -> dollar value) map."""
    frame = pd.read_csv(path)
    frame.columns = [c.strip().lower() for c in frame.columns]
    holdings: dict[str, pd.Series] = {}
    for sleeve, group in frame.groupby("sleeve"):
        holdings[str(sleeve)] = group.set_index("asset")["value"].astype(float)
    return holdings


def _load_prices(data_dir: str) -> pd.DataFrame | None:
    """Load each sleeve asset's price history for the risk flags, if present."""
    series: dict[str, pd.Series] = {}
    for sleeve in SLEEVES:
        for asset in sleeve.targets.index:
            path = Path(data_dir) / f"{asset}.csv"
            if asset not in series and path.exists():
                series[asset] = load_ohlcv(path)["close"]
    return pd.DataFrame(series) if series else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--holdings", required=True, help="CSV of current holdings")
    parser.add_argument(
        "--data-dir", help="folder of {TICKER}.csv price files (enables risk flags)"
    )
    parser.add_argument(
        "--band", type=float, default=0.05, help="rebalance band (default 5%)"
    )
    args = parser.parse_args()

    holdings = _load_holdings(args.holdings)
    prices = _load_prices(args.data_dir) if args.data_dir else None
    report = build_report(
        SLEEVES, holdings, prices=prices, rebalance_band=args.band
    )
    print()
    print(report.render())


if __name__ == "__main__":
    main()
