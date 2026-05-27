#!/usr/bin/env python3
"""Entry point: discover and backtest a portfolio of cointegrated pairs.

Examples
--------
Offline demo on a synthetic universe with embedded cointegrated clusters::

    python run_portfolio.py

Larger universe, stricter false-discovery control::

    python run_portfolio.py --clusters 5 --assets-per-cluster 5 --fdr-level 0.05

Run on real data downloaded with ``download_ibkr.py`` (one CSV per ticker)::

    python run_portfolio.py --csv-dir market_data/us_sectors \\
        --fdr-level 0.10 --lookback 500 --rebalance 60

This runs the full pipeline end to end: build a universe, discover cointegrated
pairs (correlation-distance clustering -> within-cluster cointegration ->
Benjamini-Hochberg FDR), then backtest the book with causal fractional-Kelly
weights sized off a Ledoit-Wolf covariance.
"""

from __future__ import annotations

import argparse

from dataclasses import replace

from quant_tool.backtest.portfolio import portfolio_backtest
from quant_tool.config.settings import BacktestConfig, CostConfig, PairConfig
from quant_tool.data.features import infer_bars_per_year
from quant_tool.data.ingestion import generate_universe, load_universe_from_dir
from quant_tool.monitoring import get_logger
from quant_tool.strategy.discovery import discover_pairs

log = get_logger("portfolio")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--csv-dir",
        default=None,
        help="directory of OHLCV CSVs (one per ticker) to use as the universe; "
        "if omitted, a synthetic universe is generated instead",
    )
    parser.add_argument("--bars", type=int, default=3000, help="bars per asset")
    parser.add_argument("--clusters", type=int, default=4, help="cointegrated clusters")
    parser.add_argument(
        "--assets-per-cluster", type=int, default=4, help="assets in each cluster"
    )
    parser.add_argument(
        "--noise-assets", type=int, default=4, help="independent random-walk assets"
    )
    parser.add_argument(
        "--fdr-level", type=float, default=0.10, help="Benjamini-Hochberg FDR level"
    )
    parser.add_argument(
        "--lookback", type=int, default=1000, help="Kelly estimation window (bars)"
    )
    parser.add_argument(
        "--rebalance", type=int, default=250, help="bars between weight updates"
    )
    parser.add_argument(
        "--kelly-fraction", type=float, default=0.25, help="fractional-Kelly multiplier"
    )
    parser.add_argument(
        "--asset-class",
        choices=["equity", "crypto"],
        default="equity",
        help="cost preset and calendar for annualisation (default: equity)",
    )
    parser.add_argument(
        "--bars-per-year",
        type=int,
        default=None,
        help="override the annualisation factor; otherwise inferred from --csv-dir",
    )
    args = parser.parse_args()

    if args.csv_dir:
        log.info("Loading universe from %s", args.csv_dir)
        universe = load_universe_from_dir(args.csv_dir)
    else:
        log.info("Generating a synthetic universe (offline demo)")
        universe = generate_universe(
            n_clusters=args.clusters,
            assets_per_cluster=args.assets_per_cluster,
            n_noise_assets=args.noise_assets,
            n=args.bars,
        )
    log.info("Universe: %d assets over %d bars", universe.shape[1], len(universe))

    discovery = discover_pairs(universe, fdr_level=args.fdr_level)
    log.info(discovery.describe())
    if not discovery.pairs:
        log.warning("no cointegrated pairs discovered -- nothing to backtest")
        return

    print("\n" + "-" * 60)
    print(f"{'base':<10}{'quote':<10}{'p-value':>12}{'ADF stat':>12}{'half-life':>14}")
    print("-" * 60)
    for r in discovery.pairs:
        print(
            f"{r.base:<10}{r.quote:<10}{r.pvalue:>12.4g}{r.statistic:>12.4f}"
            f"{r.half_life:>14.2f}"
        )
    print("-" * 60)

    cost = (
        CostConfig.for_crypto()
        if args.asset_class == "crypto"
        else CostConfig.for_us_equity()
    )
    if args.bars_per_year is not None:
        bpy = args.bars_per_year
    else:
        bpy = infer_bars_per_year(universe.index, asset_class=args.asset_class)
    log.info("Annualisation: bars_per_year=%d (asset_class=%s)", bpy, args.asset_class)

    config = BacktestConfig(
        pair=PairConfig(base="base", quote="quote"),
        hedge_method="kalman",
        cost=cost,
        bars_per_year=bpy,
        target_volatility=0.15,
    )
    pairs = [(result.base, result.quote) for result in discovery.pairs]
    portfolio = portfolio_backtest(
        universe,
        pairs,
        config,
        lookback=args.lookback,
        rebalance=args.rebalance,
        kelly_fraction=args.kelly_fraction,
    )
    print("\n" + "=" * 48)
    print(portfolio.describe())
    print("=" * 48)


if __name__ == "__main__":
    main()
