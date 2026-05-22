"""Portfolio weight construction.

Three methods, ordered from most robust to most data-dependent:

* :func:`strategic_weights` -- fixed target weights you choose (e.g. 70/20/10).
  Most well-structured long-term portfolios are exactly this.
* :func:`inverse_volatility_weights` -- risk-based weights, larger for calmer
  assets, so no single volatile asset dominates portfolio risk.
* :func:`minimum_variance_weights` -- the lowest-variance long-only mix.

Return *forecasts* are deliberately avoided: they are the least reliable input
and the easiest way to overfit. The covariance-based methods pair with
:func:`quant_tool.risk.portfolio.ledoit_wolf_covariance`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def strategic_weights(targets: dict[str, float] | pd.Series) -> pd.Series:
    """Fixed target weights, normalised to sum to 1.

    The simplest, most robust method: you decide the split and the portfolio
    holds it. ``targets`` maps asset name to a non-negative weight.
    """
    weights = pd.Series(targets, dtype=float)
    if weights.empty:
        raise ValueError("targets must not be empty")
    if (weights < 0).any():
        raise ValueError("strategic weights must be non-negative")
    total = weights.sum()
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    return weights / total


def inverse_volatility_weights(prices: pd.DataFrame, lookback: int = 90) -> pd.Series:
    """Risk-based weights inversely proportional to each asset's volatility.

    "Naive risk parity": a calmer asset gets a larger weight so that no single
    volatile asset dominates portfolio risk. Uses only volatility -- no return
    forecasts, no covariance inversion -- so it is stable and hard to overfit.
    """
    returns = np.log(prices).diff().dropna()
    if len(returns) < 2:
        raise ValueError("need at least 2 return observations")
    volatility = returns.tail(lookback).std()
    if (volatility <= 0).any():
        raise ValueError("an asset has zero volatility over the lookback")
    inverse = 1.0 / volatility
    return inverse / inverse.sum()


def minimum_variance_weights(
    prices: pd.DataFrame, lookback: int = 252
) -> pd.Series:
    """Long-only minimum-variance weights from a Ledoit-Wolf covariance.

    Finds the lowest-variance long-only combination of the assets. The
    shrinkage covariance keeps the optimisation well-conditioned.
    """
    from scipy.optimize import minimize

    from quant_tool.risk.portfolio import ledoit_wolf_covariance

    returns = np.log(prices).diff().dropna().tail(lookback)
    covariance = ledoit_wolf_covariance(returns).to_numpy()
    n = covariance.shape[0]

    # SLSQP's convergence tolerance is absolute; daily-return covariances are
    # ~1e-4, so the objective must be scaled up or the optimiser stops at the
    # starting point. Scaling leaves the minimiser unchanged.
    scaled = covariance * 1e4
    initial = np.full(n, 1.0 / n)
    result = minimize(
        lambda w: float(w @ scaled @ w),
        initial,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0}],
    )
    if not result.success:
        raise RuntimeError(f"minimum-variance optimisation failed: {result.message}")
    weights = np.clip(result.x, 0.0, None)
    return pd.Series(weights / weights.sum(), index=prices.columns)


def rebalancing_trades(
    current_value: pd.Series, target_weights: pd.Series
) -> pd.Series:
    """Dollar trades to move a book from its holdings to the target weights.

    ``current_value`` is the dollar value currently held in each asset.
    Returns one signed figure per asset: positive = buy, negative = sell. This
    is the output of "recommend mode" -- the trade list you place yourself.
    """
    total = float(current_value.sum())
    if total <= 0:
        raise ValueError("current portfolio value must be positive")
    target = target_weights.reindex(current_value.index).fillna(0.0)
    if target.sum() <= 0:
        raise ValueError("target weights must sum to a positive number")
    desired = total * (target / target.sum())
    return desired - current_value
