"""Tests for the backtest engine, cost model and metrics."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from quant_tool.backtest.engine import run_backtest
from quant_tool.backtest.metrics import max_drawdown, sharpe_ratio
from quant_tool.config.settings import (
    BacktestConfig,
    CostConfig,
    PairConfig,
    SignalConfig,
)
from quant_tool.data.ingestion import generate_cointegrated_pair
from quant_tool.execution.costs import CostModel

PAIR = PairConfig(base="ETH/USDT", quote="BTC/USDT")


def _config(**overrides) -> BacktestConfig:
    base = BacktestConfig(pair=PAIR, hedge_method="kalman")
    return replace(base, **overrides) if overrides else base


def test_backtest_runs_and_reports_expected_columns():
    prices = generate_cointegrated_pair(n=2000, seed=10)
    result = run_backtest(prices, _config())

    for col in ("beta", "spread", "zscore", "position", "net_return", "equity"):
        assert col in result.bars.columns
    assert len(result.bars) == len(prices)
    assert "sharpe" in result.stats
    assert result.equity.iloc[0] > 0


def test_held_position_is_lagged_signal():
    """The position earning bar t's P&L is the one set at t-1 (no look-ahead)."""
    prices = generate_cointegrated_pair(n=1500, seed=11)
    bars = run_backtest(prices, _config()).bars
    expected = bars["position"].shift(1).fillna(0.0)
    pd.testing.assert_series_equal(
        bars["held_position"], expected, check_names=False
    )


@pytest.mark.parametrize("method", ["ols", "kalman"])
def test_engine_is_look_ahead_free(method):
    """Truncating future data must not change the backtest on the prefix."""
    prices = generate_cointegrated_pair(n=2000, seed=12)
    full = run_backtest(prices, _config(hedge_method=method))
    prefix = run_backtest(prices.iloc[:1200], _config(hedge_method=method))

    pd.testing.assert_series_equal(
        full.bars["net_return"].iloc[:1200],
        prefix.bars["net_return"],
        check_names=False,
    )


def test_no_trades_keeps_capital_flat():
    """An unreachable entry threshold means no trades and a flat equity curve."""
    prices = generate_cointegrated_pair(n=1000, seed=13)
    config = _config(signal=SignalConfig(zscore_lookback=60, entry_z=99.0, stop_z=100.0))
    result = run_backtest(prices, config)

    assert result.stats["n_trades"] == 0
    assert result.equity.iloc[-1] == pytest.approx(config.initial_capital)


def test_costs_reduce_returns():
    """Adding fees can only make the net result worse than the gross result."""
    prices = generate_cointegrated_pair(n=2000, seed=14)
    free = run_backtest(prices, _config(cost=CostConfig(0.0, 0.0)))
    charged = run_backtest(prices, _config(cost=CostConfig(20.0, 10.0)))

    assert charged.equity.iloc[-1] < free.equity.iloc[-1]


def test_insufficient_history_raises():
    prices = generate_cointegrated_pair(n=50, seed=15)
    with pytest.raises(ValueError):
        run_backtest(prices, _config(signal=SignalConfig(zscore_lookback=60)))


def test_cost_model_trade_cost():
    config = CostConfig(taker_fee_bps=6.0, slippage_bps=2.0)
    model = CostModel(config, bars_per_year=8760)
    positions = pd.Series([0.0, 1.0, 1.0, -1.0, 0.0])
    cost = model.trade_cost(positions)
    # turnover magnitudes: 0, 1, 0, 2, 1 -> times cost_rate (8 bps).
    np.testing.assert_allclose(
        cost.to_numpy(), np.array([0, 1, 0, 2, 1]) * 8e-4
    )


def test_metrics_basic_properties():
    flat = pd.Series([100.0] * 10)
    assert max_drawdown(flat) == pytest.approx(0.0)
    assert sharpe_ratio(pd.Series([0.0] * 10), 8760) == 0.0
