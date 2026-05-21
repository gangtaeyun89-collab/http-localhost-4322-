"""Hedge-ratio estimation and spread construction.

The spread of a pair is ``log(base) - beta * log(quote) - alpha``. How ``beta``
is estimated determines whether the spread stays mean-reverting:

* :func:`ols_hedge_ratio` -- full-sample OLS. Convenient for research, but it
  peeks at the whole series, so it must **not** be used to drive a backtest.
* :func:`rolling_ols_hedge` -- causal rolling-window OLS, safe for backtests.
* :class:`~quant_tool.ai.kalman_filter.KalmanHedge` -- the adaptive default.

:func:`estimate_hedge` is the single entry point the backtest uses; it returns a
uniform frame (``beta, alpha, spread, zscore``) regardless of the method chosen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_tool.ai.kalman_filter import KalmanHedge


def ols_hedge_ratio(base: pd.Series, quote: pd.Series) -> tuple[float, float]:
    """Full-sample OLS of ``log(base)`` on ``log(quote)``.

    Returns ``(beta, alpha)``. Uses every observation, so it has look-ahead
    bias -- use it for research only, never to generate backtest signals.
    """
    log_base = np.log(base.to_numpy(dtype=float))
    log_quote = np.log(quote.to_numpy(dtype=float))
    design = np.column_stack([log_quote, np.ones_like(log_quote)])
    coeffs, *_ = np.linalg.lstsq(design, log_base, rcond=None)
    return float(coeffs[0]), float(coeffs[1])


def rolling_ols_hedge(
    base: pd.Series, quote: pd.Series, window: int
) -> pd.DataFrame:
    """Causal rolling-window OLS hedge ratio.

    At each bar ``t`` the estimate uses only the trailing ``window`` bars, so it
    is free of look-ahead. Returns a frame with ``beta`` and ``alpha`` columns;
    the first ``window - 1`` rows are NaN (insufficient history).
    """
    if window < 2:
        raise ValueError("window must be >= 2")
    log_base = np.log(base.astype(float))
    log_quote = np.log(quote.astype(float))

    cov = log_base.rolling(window).cov(log_quote)
    var = log_quote.rolling(window).var()
    beta = cov / var
    alpha = log_base.rolling(window).mean() - beta * log_quote.rolling(window).mean()
    return pd.DataFrame({"beta": beta, "alpha": alpha})


def compute_spread(
    base: pd.Series,
    quote: pd.Series,
    beta: pd.Series | float,
    alpha: pd.Series | float,
) -> pd.Series:
    """Hedge-adjusted residual ``log(base) - beta * log(quote) - alpha``.

    ``beta`` and ``alpha`` may be scalars or per-bar series.
    """
    return np.log(base) - beta * np.log(quote) - alpha


def _rolling_zscore(spread: pd.Series, lookback: int) -> pd.Series:
    """Trailing-window z-score; the window excludes no information after ``t``."""
    mean = spread.rolling(lookback).mean()
    std = spread.rolling(lookback).std()
    return (spread - mean) / std.replace(0.0, np.nan)


def estimate_hedge(
    base: pd.Series,
    quote: pd.Series,
    method: str,
    zscore_lookback: int,
    hedge_lookback: int = 500,
    kalman_delta: float = 1e-7,
    kalman_obs_cov: float = 1e-3,
) -> pd.DataFrame:
    """Estimate the hedge and spread for a pair, free of look-ahead bias.

    The hedge ratio and the trading signal live on different timescales, so
    they use different windows: a long ``hedge_lookback`` for a stable hedge
    ratio, and a short ``zscore_lookback`` for a responsive z-score signal.

    Parameters
    ----------
    method:
        ``"ols"`` for rolling-window OLS, ``"kalman"`` for the adaptive filter.
    zscore_lookback:
        Rolling window for the spread z-score (both methods).
    hedge_lookback:
        Rolling-OLS window for the hedge ratio. Ignored by the Kalman method,
        whose hedge timescale is governed by ``kalman_delta`` instead.

    Returns
    -------
    DataFrame with columns ``beta, alpha, spread, zscore``.
    """
    if method == "kalman":
        result = KalmanHedge(delta=kalman_delta, obs_cov=kalman_obs_cov).run(
            base, quote
        )
        # The Kalman filter's value-add is the adaptive hedge ratio. For the
        # trading signal we z-score its spread with the same empirical rolling
        # window as the OLS path: this keeps the two methods comparable and
        # avoids sensitivity to the absolute scale of ``obs_cov``. The filter's
        # own innovation-variance z-score remains available on KalmanResult.
        zscore = _rolling_zscore(result.spread, zscore_lookback)
        return pd.DataFrame(
            {
                "beta": result.beta,
                "alpha": result.alpha,
                "spread": result.spread,
                "zscore": zscore,
            }
        )

    if method == "ols":
        hedge = rolling_ols_hedge(base, quote, hedge_lookback)
        spread = compute_spread(base, quote, hedge["beta"], hedge["alpha"])
        zscore = _rolling_zscore(spread, zscore_lookback)
        return pd.DataFrame(
            {
                "beta": hedge["beta"],
                "alpha": hedge["alpha"],
                "spread": spread,
                "zscore": zscore,
            }
        )

    raise ValueError(f"unknown hedge method: {method!r}")
