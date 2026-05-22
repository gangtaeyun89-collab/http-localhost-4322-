"""Portfolio backtest: a fractional-Kelly-weighted book of pairs.

The single-pair engine (``run_backtest``) answers "how does one pair do?".
A book of pairs raises the allocation question, and answering it honestly is
where look-ahead bias creeps in -- ``Sigma^-1 mu`` is notoriously easy to
overfit. This module keeps it causal: each pair is backtested independently,
then capital is split across them by fractional-Kelly weights that are
re-estimated on a rolling *trailing* window and held forward, so no weight
ever sees the returns it is evaluated on.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_tool.backtest.engine import run_backtest
from quant_tool.backtest.metrics import cagr, max_drawdown, sharpe_ratio
from quant_tool.config.settings import BacktestConfig
from quant_tool.risk.portfolio import kelly_weights, ledoit_wolf_covariance


@dataclass(frozen=True)
class PortfolioResult:
    """Output of :func:`portfolio_backtest`.

    bars          per-bar ``portfolio_return`` and ``equity``
    pair_returns  per-pair net-return series (one column per pair)
    weights       per-pair Kelly weights over time (one column per pair)
    stats         headline portfolio performance metrics
    """

    bars: pd.DataFrame
    pair_returns: pd.DataFrame
    weights: pd.DataFrame
    stats: dict

    @property
    def equity(self) -> pd.Series:
        return self.bars["equity"]

    def describe(self) -> str:
        s = self.stats
        return (
            "Portfolio backtest (fractional-Kelly book)\n"
            f"Pairs           {s['pairs']}\n"
            f"Bars            {s['bars']}\n"
            f"Total return    {s['total_return']:+.2%}\n"
            f"CAGR            {s['cagr']:+.2%}\n"
            f"Sharpe          {s['sharpe']:.2f}\n"
            f"Annual vol      {s['annual_volatility']:.2%}\n"
            f"Max drawdown    {s['max_drawdown']:.2%}\n"
            f"Avg gross lev   {s['avg_gross_leverage']:.2f}"
        )


def portfolio_backtest(
    prices: pd.DataFrame,
    pairs: list[tuple[str, str]],
    config: BacktestConfig,
    lookback: int = 1000,
    rebalance: int = 250,
    kelly_fraction: float = 0.25,
    max_gross_leverage: float = 1.0,
) -> PortfolioResult:
    """Backtest a book of pairs sized by causal fractional-Kelly weights.

    Parameters
    ----------
    prices:
        Universe price frame, one column per asset.
    pairs:
        ``(base_column, quote_column)`` tuples -- e.g. the output of
        :func:`~quant_tool.strategy.discovery.discover_pairs`.
    config:
        Per-pair backtest configuration, applied to every pair.
    lookback:
        Trailing window (bars) for estimating each rebalance's ``mu`` and
        Ledoit-Wolf covariance.
    rebalance:
        Bars between weight updates; weights are held constant in between.
    kelly_fraction, max_gross_leverage:
        Passed to :func:`~quant_tool.risk.portfolio.kelly_weights`.
    """
    if not pairs:
        raise ValueError("pairs must be a non-empty list")
    if rebalance < 1:
        raise ValueError("rebalance must be >= 1")
    n = len(prices)
    if n <= lookback:
        raise ValueError(f"need more than lookback={lookback} bars, got {n}")

    # --- 1. one independent single-pair backtest per pair --------------------
    columns: dict[str, pd.Series] = {}
    for base_col, quote_col in pairs:
        pair_prices = pd.DataFrame(
            {"base": prices[base_col], "quote": prices[quote_col]}
        )
        result = run_backtest(pair_prices, config)
        columns[f"{base_col}~{quote_col}"] = result.bars["net_return"]
    pair_returns = pd.DataFrame(columns)

    # --- 2. causal fractional-Kelly weights, refreshed every `rebalance` -----
    # The weights applied over [r, r + rebalance) are estimated from the
    # trailing window [r - lookback, r): strictly past data, no look-ahead.
    weights = pd.DataFrame(
        0.0, index=pair_returns.index, columns=pair_returns.columns
    )
    for r in range(lookback, n, rebalance):
        window = pair_returns.iloc[r - lookback : r]
        mu = window.mean()
        covariance = ledoit_wolf_covariance(window)
        block_weights = kelly_weights(
            mu, covariance, kelly_fraction, max_gross_leverage
        )
        weights.iloc[r : r + rebalance] = block_weights.to_numpy()

    # --- 3. portfolio return and equity --------------------------------------
    portfolio_return = (weights * pair_returns).sum(axis=1)
    equity = config.initial_capital * (1.0 + portfolio_return).cumprod()

    gross_leverage = weights.abs().sum(axis=1)
    stats = {
        "pairs": len(pairs),
        "bars": n,
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1.0),
        "cagr": cagr(equity, config.bars_per_year),
        "sharpe": sharpe_ratio(portfolio_return, config.bars_per_year),
        "annual_volatility": float(
            portfolio_return.std() * np.sqrt(config.bars_per_year)
        ),
        "max_drawdown": max_drawdown(equity),
        "avg_gross_leverage": float(gross_leverage.iloc[lookback:].mean()),
    }
    bars = pd.DataFrame(
        {"portfolio_return": portfolio_return, "equity": equity}
    )
    return PortfolioResult(
        bars=bars, pair_returns=pair_returns, weights=weights, stats=stats
    )
