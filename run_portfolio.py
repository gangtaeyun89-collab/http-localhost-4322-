#!/usr/bin/env python3
"""Entry point: discover and backtest a portfolio of cointegrated pairs.

Examples
--------
Offline demo on a synthetic universe with embedded cointegrated clusters::

    python run_portfolio.py

Larger universe, stricter false-discovery control::

    python run_portfolio.py --clusters 5 --assets-per-cluster 5 --fdr-level 0.05

This runs the full pipeline end to end: build a universe, discover cointegrated
pairs (correlation-distance clustering -> within-cluster cointegration ->
Benjamini-Hochberg FDR), then backtest the book with causal fractional-Kelly
weights sized off a Ledoit-Wolf covariance.
"""

from __future__ import annotations

import argparse

from quant_tool.backtest.portfolio import portfolio_backtest
from quant_tool.config.settings import BacktestConfig, PairConfig
from quant_tool.data.ingestion import generate_universe
from quant_tool.monitoring import get_logger
from quant_tool.strategy.discovery import discover_pairs

log = get_logger("portfolio")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
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
    args = parser.parse_args()

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

    config = BacktestConfig(
        pair=PairConfig(base="base", quote="quote"),
        hedge_method="kalman",
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
