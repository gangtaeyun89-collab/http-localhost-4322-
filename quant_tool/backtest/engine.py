"""Vectorised, look-ahead-free backtest engine for spread trading.

Timing convention -- the single most important thing for a trustworthy result:

* the hedge, spread and z-score at bar ``t`` use only data up to ``t``;
* a signal computed at the close of bar ``t`` sets the target position for
  ``t``, and trading costs are charged at ``t``;
* the position carried *into* bar ``t`` is the one set at ``t - 1``
  (``held_position``), and that is what earns bar ``t``'s spread return.

Because every forward-looking quantity is explicitly ``shift``-ed, the engine
cannot use information that would not have been available in real time. The
same :func:`run_backtest` would drive a paper-trading loop if fed a live,
growing price frame.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_tool.config.settings import BacktestConfig
from quant_tool.data.features import log_returns
from quant_tool.execution.costs import CostModel
from quant_tool.risk.sizing import vol_target_multiplier
from quant_tool.strategy.signals import generate_positions
from quant_tool.strategy.spread import estimate_hedge


@dataclass(frozen=True)
class BacktestResult:
    """Output of :func:`run_backtest`.

    bars    per-bar DataFrame: prices, hedge, signal, positions, returns, equity
    stats   headline and trade-level performance metrics
    config  the configuration the run used
    """

    bars: pd.DataFrame
    stats: dict
    config: BacktestConfig

    @property
    def equity(self) -> pd.Series:
        return self.bars["equity"]

    def describe(self) -> str:
        """Human-readable one-block summary of the run."""
        s = self.stats
        return (
            f"Pair            {self.config.pair.name}\n"
            f"Hedge method    {self.config.hedge_method}\n"
            f"Bars            {s['bars']}\n"
            f"Total return    {s['total_return']:+.2%}\n"
            f"CAGR            {s['cagr']:+.2%}\n"
            f"Sharpe          {s['sharpe']:.2f}\n"
            f"Annual vol      {s['annual_volatility']:.2%}\n"
            f"Max drawdown    {s['max_drawdown']:.2%}\n"
            f"Trades          {s['n_trades']}\n"
            f"Win rate        {s['win_rate']:.2%}\n"
            f"Avg trade       {s['avg_trade_return']:+.2%}\n"
            f"Avg holding     {s['avg_holding_bars']:.1f} bars"
        )


def run_backtest(prices: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
    """Run a spread-trading backtest.

    Parameters
    ----------
    prices:
        DataFrame with ``base`` and ``quote`` price columns sharing one index.
    config:
        Strategy, cost and risk configuration.
    """
    from quant_tool.backtest.metrics import performance_summary

    if not {"base", "quote"}.issubset(prices.columns):
        raise ValueError("prices must have 'base' and 'quote' columns")
    warmup = config.hedge_lookback if config.hedge_method == "ols" else 0
    if len(prices) < warmup + config.signal.zscore_lookback + 2:
        raise ValueError("not enough price history for the configured lookbacks")

    base = prices["base"].astype(float)
    quote = prices["quote"].astype(float)

    # --- strategy layer: hedge, spread, z-score, target signal ---------------
    hedge = estimate_hedge(
        base,
        quote,
        config.hedge_method,
        config.signal.zscore_lookback,
        config.hedge_lookback,
    )
    target_position = generate_positions(hedge["zscore"], config.signal)

    # --- spread return earned by holding one unit of long-spread exposure ----
    # beta is shifted: the hedge ratio used over bar t is the one known at t-1.
    beta_used = hedge["beta"].shift(1)
    gross_exposure = 1.0 + beta_used.abs()
    spread_return = (
        log_returns(base) - beta_used * log_returns(quote)
    ) / gross_exposure

    # --- risk layer: optional volatility-targeted sizing ---------------------
    if config.target_volatility is not None:
        multiplier = vol_target_multiplier(
            spread_return.fillna(0.0),
            config.target_volatility,
            config.vol_lookback,
            config.bars_per_year,
            config.max_leverage,
        )
    else:
        multiplier = pd.Series(1.0, index=prices.index)
    position = target_position * multiplier

    # --- P&L: held position earns this bar's spread return -------------------
    held_position = position.shift(1).fillna(0.0)
    gross_return = (held_position * spread_return).fillna(0.0)

    costs = CostModel(config.cost, config.bars_per_year)
    trade_cost = costs.trade_cost(position)
    funding_cost = costs.funding_cost(position)
    net_return = (gross_return - trade_cost - funding_cost).fillna(0.0)

    equity = config.initial_capital * (1.0 + net_return).cumprod()

    bars = pd.DataFrame(
        {
            "base": base,
            "quote": quote,
            "beta": hedge["beta"],
            "alpha": hedge["alpha"],
            "spread": hedge["spread"],
            "zscore": hedge["zscore"],
            "target_position": target_position,
            "position": position,
            "held_position": held_position,
            "spread_return": spread_return,
            "gross_return": gross_return,
            "trade_cost": trade_cost,
            "funding_cost": funding_cost,
            "net_return": net_return,
            "equity": equity,
        }
    )
    stats = performance_summary(
        net_return, equity, held_position, config.bars_per_year
    )
    return BacktestResult(bars=bars, stats=stats, config=config)
