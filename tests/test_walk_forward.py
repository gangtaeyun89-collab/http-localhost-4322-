"""Tests for the walk-forward out-of-sample evaluation framework."""

import pandas as pd
import pytest

from quant_tool.backtest.walk_forward import walk_forward
from quant_tool.config.settings import BacktestConfig, PairConfig
from quant_tool.data.ingestion import generate_cointegrated_pair

PAIR = PairConfig(base="ETH", quote="BTC")


def test_walk_forward_runs_and_tiles_windows():
    prices = generate_cointegrated_pair(n=2400, seed=50)
    result = walk_forward(prices, BacktestConfig(pair=PAIR), train_size=800, test_size=400)

    assert len(result.windows) >= 2
    # consecutive test windows tile the timeline with no gap or overlap
    assert len(result.bars) == len(result.windows) * 400
    assert "sharpe" in result.stats
    assert result.equity.iloc[0] > 0


def test_walk_forward_is_lookahead_free():
    """Window i's parameter choice and result must not depend on later bars."""
    prices_long = generate_cointegrated_pair(n=3000, seed=51)
    prices_short = prices_long.iloc[:2200]
    config = BacktestConfig(pair=PAIR)
    grid = {"entry_z": [1.5, 2.0, 2.5]}

    wf_short = walk_forward(prices_short, config, 800, 400, param_grid=grid)
    wf_long = walk_forward(prices_long, config, 800, 400, param_grid=grid)

    shared = len(wf_short.windows)
    assert shared >= 2
    for i in range(shared):
        assert wf_short.windows[i].params == wf_long.windows[i].params
        assert wf_short.windows[i].train_sharpe == pytest.approx(
            wf_long.windows[i].train_sharpe
        )
    pd.testing.assert_series_equal(
        wf_short.bars["net_return"].reset_index(drop=True),
        wf_long.bars["net_return"].iloc[: len(wf_short.bars)].reset_index(drop=True),
    )


def test_walk_forward_grid_selects_from_the_grid():
    prices = generate_cointegrated_pair(n=2800, seed=52)
    grid = {"entry_z": [1.5, 2.5]}
    result = walk_forward(prices, BacktestConfig(pair=PAIR), 900, 400, param_grid=grid)

    assert result.windows
    for window in result.windows:
        assert window.params["entry_z"] in (1.5, 2.5)


def test_walk_forward_rejects_insufficient_data():
    prices = generate_cointegrated_pair(n=500, seed=53)
    with pytest.raises(ValueError):
        walk_forward(prices, BacktestConfig(pair=PAIR), train_size=800, test_size=400)


def test_walk_forward_rejects_unknown_grid_key():
    prices = generate_cointegrated_pair(n=2400, seed=54)
    with pytest.raises(ValueError):
        walk_forward(
            prices, BacktestConfig(pair=PAIR), 800, 400, param_grid={"not_a_field": [1]}
        )
