"""Backtest a buy-hold-rebalance portfolio.

This is the core of a "well-structured portfolio": pick target weights, hold
them, and rebalance back to target on a fixed schedule. The backtest is
strictly causal -- dynamic weight rules only ever see trailing data -- so the
result is an honest estimate, not a hindsight-fitted one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_tool.backtest.metrics import cagr, max_drawdown, sharpe_ratio

WeightSpec = pd.Series | Callable[[pd.DataFrame], pd.Series]


@dataclass(frozen=True)
class AllocationResult:
    """Output of :func:`backtest_allocation`.

    equity   portfolio value over time
    weights  realised per-asset weights over time
    stats    headline performance metrics
    """

    equity: pd.Series
    weights: pd.DataFrame
    stats: dict

    def describe(self) -> str:
        s = self.stats
        return (
            "Portfolio allocation backtest\n"
            f"Assets          {s['assets']}\n"
            f"Total return    {s['total_return']:+.2%}\n"
            f"CAGR            {s['cagr']:+.2%}\n"
            f"Annual vol      {s['annual_volatility']:.2%}\n"
            f"Sharpe          {s['sharpe']:.2f}\n"
            f"Max drawdown    {s['max_drawdown']:.2%}\n"
            f"Rebalances      {s['rebalances']}"
        )


def backtest_allocation(
    prices: pd.DataFrame,
    target_weights: WeightSpec,
    rebalance_every: int = 63,
    lookback: int = 252,
    initial_capital: float = 10_000.0,
    cost_bps: float = 10.0,
    bars_per_year: int = 252,
) -> AllocationResult:
    """Backtest holding ``target_weights`` and rebalancing on a schedule.

    Parameters
    ----------
    prices:
        One price column per asset, on a shared index.
    target_weights:
        Either a fixed ``Series`` of weights (strategic), or a callable mapping
        a trailing-price DataFrame to a weight Series (risk-based methods). A
        callable is only ever given past data, so there is no look-ahead.
    rebalance_every:
        Bars between rebalances (default ~quarterly on daily data).
    lookback:
        Trailing window handed to a callable ``target_weights``.
    cost_bps:
        Round-trip cost charged on rebalancing turnover.
    """
    prices = prices.dropna()
    n = len(prices)
    is_dynamic = callable(target_weights)
    start = lookback if is_dynamic else 1
    if start >= n:
        raise ValueError("not enough price history for the configured lookback")
    if rebalance_every < 1:
        raise ValueError("rebalance_every must be >= 1")

    returns = prices.pct_change()
    assets = list(prices.columns)

    def weights_at(t: int) -> pd.Series:
        if is_dynamic:
            w = target_weights(prices.iloc[:t])  # strictly trailing data
        else:
            w = pd.Series(target_weights, dtype=float)
        w = w.reindex(assets).fillna(0.0)
        return w / w.sum()

    equity = np.full(n, initial_capital, dtype=float)
    weight_rows: dict = {}

    # Invest at bar `start` using weights from data up to start - 1.
    holdings = initial_capital * (1.0 - cost_bps / 1e4) * weights_at(start)
    equity[start] = holdings.sum()
    weight_rows[prices.index[start]] = holdings / holdings.sum()
    rebalances = 0

    for t in range(start + 1, n):
        holdings = holdings * (1.0 + returns.iloc[t])
        value = float(holdings.sum())
        if (t - start) % rebalance_every == 0:
            target = weights_at(t)
            desired = value * target
            turnover = float((desired - holdings).abs().sum())
            value -= turnover * cost_bps / 1e4
            holdings = value * target
            rebalances += 1
        equity[t] = value
        weight_rows[prices.index[t]] = holdings / value

    equity_series = pd.Series(equity, index=prices.index, name="equity")
    portfolio_returns = equity_series.pct_change().fillna(0.0)
    stats = {
        "assets": len(assets),
        "total_return": float(equity_series.iloc[-1] / initial_capital - 1.0),
        "cagr": cagr(equity_series, bars_per_year),
        "annual_volatility": float(
            portfolio_returns.iloc[start:].std() * np.sqrt(bars_per_year)
        ),
        "sharpe": sharpe_ratio(portfolio_returns.iloc[start:], bars_per_year),
        "max_drawdown": max_drawdown(equity_series),
        "rebalances": rebalances,
    }
    return AllocationResult(
        equity=equity_series,
        weights=pd.DataFrame(weight_rows).T,
        stats=stats,
    )
