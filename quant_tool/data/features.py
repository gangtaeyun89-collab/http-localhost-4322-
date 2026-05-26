"""Feature computation shared by the strategy and backtest layers."""

from __future__ import annotations

import numpy as np
import pandas as pd


# Bars per calendar year by per-bar seconds. US equities trade ~252 sessions
# of 6.5 hours per year; crypto runs 24/7 (365 days). Passing the wrong factor
# to the Sharpe/CAGR/target-vol calculations silently rescales every result by
# a constant -- the canonical "Sharpe inflated 5.9x" bug -- so we infer it
# from the data instead of relying on a default.
_EQUITY_BARS_PER_YEAR: tuple[tuple[float, int], ...] = (
    (1.0, int(252 * 6.5 * 60 * 60)),   # 1s
    (60.0, int(252 * 6.5 * 60)),        # 1m
    (300.0, int(252 * 6.5 * 12)),       # 5m
    (900.0, int(252 * 6.5 * 4)),        # 15m
    (1800.0, int(252 * 6.5 * 2)),       # 30m
    (3600.0, int(252 * 6.5)),           # 1h
    (14_400.0, int(252 * 6.5 / 4)),     # 4h
    (86_400.0, 252),                    # 1d
    (86_400.0 * 7, 52),                 # 1w
    (86_400.0 * 30, 12),                # 1M
)

_CRYPTO_BARS_PER_YEAR: tuple[tuple[float, int], ...] = (
    (1.0, 365 * 24 * 60 * 60),
    (60.0, 365 * 24 * 60),
    (300.0, 365 * 24 * 12),
    (900.0, 365 * 24 * 4),
    (1800.0, 365 * 24 * 2),
    (3600.0, 365 * 24),                 # 1h (=8760)
    (14_400.0, 365 * 6),                # 4h
    (86_400.0, 365),                    # 1d
)


def infer_bars_per_year(
    index: pd.DatetimeIndex, asset_class: str = "equity"
) -> int:
    """Infer the annualisation factor from a bar's timestamp spacing.

    Uses the median gap between consecutive bars and picks the timeframe whose
    seconds-per-bar is closest in log space. ``asset_class`` selects the
    calendar: ``"equity"`` for US sessions (252 days x 6.5 hours), ``"crypto"``
    for 24/7 markets. Falls back to 252 (daily equities) if the index is too
    short to measure.

    Mis-annualising silently rescales Sharpe, CAGR, and any vol-target
    sizing -- always pass the resulting value into ``BacktestConfig``.
    """
    if len(index) < 2:
        return 252
    # The underlying integer unit of a DatetimeIndex varies (ns/us/ms) by dtype
    # and pandas version; ``.total_seconds()`` on a Timedelta is invariant.
    diffs = pd.Series(index).diff().dropna()
    median = float(diffs.median().total_seconds())
    if median <= 0:
        return 252
    table = _CRYPTO_BARS_PER_YEAR if asset_class == "crypto" else _EQUITY_BARS_PER_YEAR
    closest = min(table, key=lambda kv: abs(np.log(kv[0] / median)))
    return closest[1]


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
