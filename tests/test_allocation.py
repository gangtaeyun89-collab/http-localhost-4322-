"""Tests for the portfolio allocation engine."""

import numpy as np
import pandas as pd
import pytest

from quant_tool.allocation.backtest import backtest_allocation
from quant_tool.allocation.construction import (
    inverse_volatility_weights,
    minimum_variance_weights,
    rebalancing_trades,
    strategic_weights,
)
from quant_tool.data.ingestion import generate_universe


def test_strategic_weights_normalise():
    weights = strategic_weights({"a": 3.0, "b": 1.0})
    assert weights.sum() == pytest.approx(1.0)
    assert weights["a"] == pytest.approx(0.75)


def test_strategic_weights_reject_negative():
    with pytest.raises(ValueError):
        strategic_weights({"a": 1.0, "b": -0.5})


def test_inverse_volatility_favours_the_calmer_asset():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-01", periods=300, freq="D")
    calm = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, 300)))
    wild = 100 * np.exp(np.cumsum(rng.normal(0, 0.030, 300)))
    prices = pd.DataFrame({"calm": calm, "wild": wild}, index=idx)

    weights = inverse_volatility_weights(prices)
    assert weights["calm"] > weights["wild"]
    assert weights.sum() == pytest.approx(1.0)


def test_minimum_variance_has_low_realised_variance():
    prices = generate_universe(n=1200, seed=70)
    returns = np.log(prices).diff().dropna()
    mv = minimum_variance_weights(prices)
    equal = pd.Series(1.0 / prices.shape[1], index=prices.columns)

    assert (returns @ mv).std() <= (returns @ equal).std()
    assert mv.min() >= -1e-9
    assert mv.sum() == pytest.approx(1.0)


def test_rebalancing_trades_move_to_target_and_net_to_zero():
    current = pd.Series({"a": 6000.0, "b": 4000.0})
    target = pd.Series({"a": 0.5, "b": 0.5})
    trades = rebalancing_trades(current, target)
    assert trades.sum() == pytest.approx(0.0)  # an internal rebalance nets to 0
    assert trades["a"] == pytest.approx(-1000.0)
    assert trades["b"] == pytest.approx(1000.0)


def test_backtest_allocation_runs_with_fixed_weights():
    prices = generate_universe(n=1500, seed=71)
    weights = strategic_weights({c: 1.0 for c in prices.columns})
    result = backtest_allocation(prices, weights, rebalance_every=63)

    assert result.equity.iloc[-1] > 0
    assert result.stats["rebalances"] > 0
    assert "max_drawdown" in result.stats


def test_backtest_allocation_is_lookahead_free():
    """A dynamic weight rule must not let later bars change earlier equity."""
    prices = generate_universe(n=1800, seed=72)
    cut = 1200
    full = backtest_allocation(
        prices, inverse_volatility_weights, rebalance_every=63, lookback=252
    )
    prefix = backtest_allocation(
        prices.iloc[:cut], inverse_volatility_weights,
        rebalance_every=63, lookback=252,
    )
    pd.testing.assert_series_equal(
        full.equity.iloc[:cut].reset_index(drop=True),
        prefix.equity.reset_index(drop=True),
    )


def test_backtest_allocation_costs_reduce_equity():
    prices = generate_universe(n=1200, seed=73)
    weights = strategic_weights({c: 1.0 for c in prices.columns})
    free = backtest_allocation(prices, weights, rebalance_every=21, cost_bps=0.0)
    costly = backtest_allocation(prices, weights, rebalance_every=21, cost_bps=100.0)
    assert costly.equity.iloc[-1] < free.equity.iloc[-1]
