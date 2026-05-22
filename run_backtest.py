#!/usr/bin/env python3
"""Entry point: run a crypto pairs-trading backtest.

Examples
--------
Offline demo on a synthetic cointegrated pair (no network, no API keys)::

    python run_backtest.py

Compare the static OLS hedge against the adaptive Kalman hedge::

    python run_backtest.py --compare

Pull real candles from an exchange via ccxt::

    python run_backtest.py --config quant_tool/config/pairs.yaml --fetch

Validate on real data you have exported to CSV/Parquet (no network needed)::

    python run_backtest.py --base-csv eth.csv --quote-csv btc.csv

This is the runnable MVP for steps 1-2 of the build plan: get data, hedge a
pair, backtest with realistic fees, and report honest metrics.
"""

from __future__ import annotations

import argparse
from dataclasses import replace

import pandas as pd

from quant_tool.ai.kalman_filter import KalmanHedge
from quant_tool.backtest.engine import run_backtest
from quant_tool.config.settings import BacktestConfig, PairConfig, load_config
from quant_tool.data.features import align_prices
from quant_tool.data.ingestion import (
    fetch_ohlcv,
    generate_cointegrated_pair,
    load_pair,
)
from quant_tool.monitoring import get_logger
from quant_tool.strategy.pair_finder import cointegration_test

log = get_logger("backtest")


def _load_prices(args: argparse.Namespace, config: BacktestConfig) -> pd.DataFrame:
    """Load aligned base/quote prices from the chosen source.

    Precedence: exported CSV/Parquet files, then a live exchange fetch, then
    the offline synthetic generator.
    """
    if args.base_csv:
        log.info("Loading candles from %s and %s", args.base_csv, args.quote_csv)
        return load_pair(args.base_csv, args.quote_csv)

    if args.fetch:
        log.info("Fetching %s candles from the exchange", config.pair.name)
        base = fetch_ohlcv(config.pair.base, config.pair.timeframe, args.bars)["close"]
        quote = fetch_ohlcv(config.pair.quote, config.pair.timeframe, args.bars)["close"]
        return align_prices(base, quote)

    log.info("Generating a synthetic cointegrated pair (offline demo)")
    # A slowly drifting hedge ratio mimics real crypto pairs and is the regime
    # where the adaptive Kalman hedge is worth comparing against static OLS.
    return generate_cointegrated_pair(n=args.bars, beta_drift_vol=0.0008)


def _screen(prices: pd.DataFrame) -> None:
    """Print a cointegration screen; degrade gracefully without statsmodels."""
    try:
        result = cointegration_test(prices["base"], prices["quote"])
    except ImportError:
        log.warning("statsmodels not installed -- skipping cointegration screen")
        return
    except Exception as exc:  # degenerate input (zero variance, too short, ...)
        log.warning("cointegration screen skipped: %s", exc)
        return
    verdict = "COINTEGRATED" if result.is_cointegrated else "not cointegrated"
    log.info(
        "Cointegration screen: p=%.4f, half-life=%.1f bars -> %s",
        result.pvalue,
        result.half_life,
        verdict,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", help="path to a YAML BacktestConfig")
    parser.add_argument("--fetch", action="store_true", help="fetch live data via ccxt")
    parser.add_argument(
        "--base-csv", help="CSV/Parquet OHLCV file for the base leg"
    )
    parser.add_argument(
        "--quote-csv", help="CSV/Parquet OHLCV file for the quote leg"
    )
    parser.add_argument(
        "--bars", type=int, default=3000, help="number of bars (fetch/synthetic only)"
    )
    parser.add_argument(
        "--method", choices=["ols", "kalman"], help="override the hedge method"
    )
    parser.add_argument(
        "--compare", action="store_true", help="run both OLS and Kalman side by side"
    )
    parser.add_argument(
        "--fit-kalman",
        action="store_true",
        help="tune the Kalman delta by maximum likelihood "
        "(prediction-optimal, not necessarily P&L-optimal -- see KalmanHedge.fit)",
    )
    args = parser.parse_args()

    if bool(args.base_csv) != bool(args.quote_csv):
        parser.error("--base-csv and --quote-csv must be given together")

    if args.config:
        config = load_config(args.config)
    else:
        config = BacktestConfig(
            pair=PairConfig(base="ETH/USDT", quote="BTC/USDT"),
            target_volatility=0.15,
        )
    if args.method:
        config = replace(config, hedge_method=args.method)

    prices = _load_prices(args, config)
    log.info("Loaded %d aligned bars", len(prices))
    _screen(prices)

    methods = ["ols", "kalman"] if args.compare else [config.hedge_method]

    if args.fit_kalman and "kalman" in methods:
        fitted = KalmanHedge.fit(prices["base"], prices["quote"])
        log.info(
            "Fitted Kalman delta by maximum likelihood: %.2e (default was %.2e)",
            fitted.delta,
            config.kalman_delta,
        )
        config = replace(config, kalman_delta=fitted.delta)

    for method in methods:
        try:
            result = run_backtest(prices, replace(config, hedge_method=method))
        except ValueError as exc:
            # One method failing (e.g. too few bars for the OLS warm-up) must
            # not abort the others in a --compare run.
            log.warning("skipping %s: %s", method, exc)
            continue
        print("\n" + "=" * 48)
        print(result.describe())
    print("=" * 48)


if __name__ == "__main__":
    main()
