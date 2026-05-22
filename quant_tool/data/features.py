"""Feature computation shared by the strategy and backtest layers."""

from __future__ import annotations

import numpy as np
import pandas as pd


def log_returns(prices: pd.Series) -> pd.Series:
    """Bar-over-bar log returns. The first observation is 0 (no prior bar)."""
    return np.log(prices).diff().fillna(0.0)


def simple_returns(prices: pd.Series) -> pd.Series:
    """Bar-over-bar simple returns. The first observation is 0."""
    return prices.pct_change().fillna(0.0)


def align_prices(base: pd.Series, quote: pd.Series) -> pd.DataFrame:
    """Inner-join two price series on their index and drop any gaps.

    Returns a DataFrame with columns ``base`` and ``quote``. Aligning before any
    other computation is what keeps the two legs time-consistent.
    """
    df = pd.concat([base.rename("base"), quote.rename("quote")], axis=1)
    return df.dropna()
