"""Position sizing and risk scaling.

The strategy layer emits unit positions in ``{-1, 0, +1}``. This module turns
those into risk-aware sizes by scaling each trade so it carries a comparable
amount of risk regardless of how volatile the spread currently is.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def realized_volatility(
    returns: pd.Series, window: int, bars_per_year: int
) -> pd.Series:
    """Annualised trailing realised volatility of a return series."""
    if window < 2:
        raise ValueError("window must be >= 2")
    return returns.rolling(window).std() * np.sqrt(bars_per_year)


def vol_target_multiplier(
    spread_returns: pd.Series,
    target_annual_vol: float,
    window: int,
    bars_per_year: int,
    max_leverage: float = 3.0,
) -> pd.Series:
    """Per-bar size multiplier that targets a constant spread risk budget.

    The multiplier is ``target_vol / realised_vol`` of the spread, clipped to
    ``max_leverage``. It is shifted one bar so the size used on bar ``t`` is
    derived only from data available at ``t - 1`` -- no look-ahead.
    """
    if target_annual_vol <= 0:
        raise ValueError("target_annual_vol must be positive")
    vol = realized_volatility(spread_returns, window, bars_per_year)
    # A zero-volatility window gives no usable estimate; dividing by it would
    # otherwise pin the size at max_leverage right after a dead-volatility
    # stretch. Treat it (and the warm-up NaNs) as unit size instead.
    multiplier = (target_annual_vol / vol.where(vol > 0)).clip(upper=max_leverage)
    return multiplier.shift(1).fillna(1.0)
