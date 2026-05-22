"""Portfolio-level position sizing across many pairs.

Single-pair volatility targeting (``risk/sizing.py``) decides how large one
spread trade is. Trading a *book* of pairs raises a second question: how to
split capital between them.

The Kelly criterion gives the growth-optimal split, ``f* = Sigma^-1 mu``. The
catch is that the sample covariance ``Sigma`` is ill-conditioned when pairs are
numerous or correlated, so ``Sigma^-1`` blows up into huge offsetting bets that
have nothing to do with edge. Ledoit-Wolf shrinkage repairs the conditioning,
and *fractional* Kelly tames the well-documented over-betting of full Kelly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ledoit_wolf_covariance(returns: pd.DataFrame) -> pd.DataFrame:
    """Ledoit-Wolf shrinkage covariance of per-asset (or per-pair) returns.

    Wraps the canonical scikit-learn estimator. The shrinkage pulls the
    ill-conditioned sample covariance toward a scaled-identity target, keeping
    it well-conditioned and invertible -- essential before forming Kelly
    weights, and the difference between a sane book and nonsense leverage.

    ``returns`` has one column per asset; rows are aligned observations.
    """
    try:
        from sklearn.covariance import ledoit_wolf
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "ledoit_wolf_covariance requires the optional 'scikit-learn' "
            "dependency: pip install scikit-learn"
        ) from exc

    clean = returns.dropna()
    if clean.shape[0] < 2:
        raise ValueError("need at least 2 return observations")
    if clean.shape[1] < 1:
        raise ValueError("need at least one asset column")

    covariance, _shrinkage = ledoit_wolf(clean.to_numpy(dtype=float))
    return pd.DataFrame(
        covariance, index=returns.columns, columns=returns.columns
    )


def kelly_weights(
    expected_returns: pd.Series,
    covariance: pd.DataFrame,
    fraction: float = 0.25,
    max_gross_leverage: float = 1.0,
) -> pd.Series:
    """Fractional-Kelly portfolio weights, ``f = fraction * Sigma^-1 * mu``.

    Full Kelly (``fraction = 1``) maximises long-run log-growth but is far too
    aggressive once ``mu`` and ``Sigma`` carry estimation error -- full-Kelly
    drawdowns of 40-50% are typical. A fraction of 0.25-0.5 is standard.

    If the resulting gross leverage (sum of absolute weights) exceeds
    ``max_gross_leverage`` the whole vector is scaled down to that cap, so the
    book never silently levers itself up through a near-singular covariance.
    """
    if not 0.0 < fraction <= 1.0:
        raise ValueError("fraction must be in (0, 1]")
    if max_gross_leverage <= 0.0:
        raise ValueError("max_gross_leverage must be positive")
    if not covariance.index.equals(expected_returns.index):
        raise ValueError("covariance and expected_returns must be aligned")
    if not covariance.index.equals(covariance.columns):
        raise ValueError("covariance must be square with matching labels")

    mu = expected_returns.to_numpy(dtype=float)
    sigma = covariance.to_numpy(dtype=float)
    # Sigma is positive-definite when it comes from ledoit_wolf_covariance,
    # so the linear solve is stable and avoids an explicit inverse.
    raw = np.linalg.solve(sigma, mu)
    weights = fraction * raw

    gross = float(np.abs(weights).sum())
    if gross > max_gross_leverage:
        weights = weights * (max_gross_leverage / gross)
    return pd.Series(weights, index=expected_returns.index, name="weight")
