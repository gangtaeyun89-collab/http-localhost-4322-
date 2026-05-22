"""Tests for the Kelly-weighted portfolio backtest."""

import pandas as pd
import pytest

from quant_tool.backtest.portfolio import portfolio_backtest
from quant_tool.config.settings import BacktestConfig, PairConfig
from quant_tool.data.ingestion import generate_universe

CONFIG = BacktestConfig(pair=PairConfig("x", "y"), hedge_method="kalman")
PAIRS = [
    ("c0_a0", "c0_a1"),
    ("c0_a0", "c0_a2"),
    ("c1_a0", "c1_a1"),
    ("c1_a0", "c1_a2"),
]


def test_portfolio_backtest_runs_with_expected_shapes():
    universe = generate_universe(
        n_clusters=2, assets_per_cluster=3, n_noise_assets=2, n=2000, seed=60
    )
    result = portfolio_backtest(universe, PAIRS, CONFIG, lookback=600, rebalance=300)

    assert result.pair_returns.shape == (2000, len(PAIRS))
    assert result.weights.shape == (2000, len(PAIRS))
    assert len(result.bars) == 2000
    assert result.stats["pairs"] == len(PAIRS)
    assert result.equity.iloc[0] > 0


def test_portfolio_weights_are_causal_and_capped():
    universe = generate_universe(
        n_clusters=2, assets_per_cluster=3, n_noise_assets=2, n=2000, seed=61
    )
    lookback = 600
    result = portfolio_backtest(
        universe, PAIRS, CONFIG, lookback=lookback, rebalance=300,
        max_gross_leverage=1.0,
    )
    # no weight is assigned before enough history exists
    assert (result.weights.iloc[:lookback] == 0.0).all().all()
    # gross leverage never exceeds the cap once trading starts
    gross = result.weights.abs().sum(axis=1).iloc[lookback:]
    assert gross.max() <= 1.0 + 1e-9


def test_portfolio_backtest_is_lookahead_free():
    """The portfolio return on the first N bars must not depend on later bars."""
    universe = generate_universe(
        n_clusters=2, assets_per_cluster=3, n_noise_assets=2, n=2000, seed=62
    )
    cut = 1500
    full = portfolio_backtest(universe, PAIRS, CONFIG, lookback=600, rebalance=300)
    prefix = portfolio_backtest(
        universe.iloc[:cut], PAIRS, CONFIG, lookback=600, rebalance=300
    )
    pd.testing.assert_series_equal(
        full.bars["portfolio_return"].iloc[:cut].reset_index(drop=True),
        prefix.bars["portfolio_return"].reset_index(drop=True),
    )


def test_portfolio_backtest_rejects_empty_pairs():
    universe = generate_universe(n=1500, seed=63)
    with pytest.raises(ValueError):
        portfolio_backtest(universe, [], CONFIG, lookback=600)


def test_portfolio_backtest_rejects_insufficient_data():
    universe = generate_universe(n=500, seed=64)
    with pytest.raises(ValueError):
        portfolio_backtest(universe, PAIRS, CONFIG, lookback=600)
