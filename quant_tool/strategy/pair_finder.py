"""Pair discovery: cointegration testing and mean-reversion diagnostics.

Statistical arbitrage only works on pairs whose spread is genuinely
mean-reverting. These helpers screen candidates *before* they reach the
backtest. Always re-run the screen on a rolling basis: a pair that cointegrated
last quarter may not next quarter, and selecting pairs because they cointegrated
inside the test window (survivorship bias) inflates backtest Sharpe ratios.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CointegrationResult:
    base: str
    quote: str
    pvalue: float
    statistic: float
    half_life: float

    @property
    def is_cointegrated(self) -> bool:
        """True at the conventional 5% significance level."""
        return self.pvalue < 0.05


def half_life(spread: pd.Series) -> float:
    """Estimate the mean-reversion half-life of a spread, in bars.

    Fits the AR(1) model ``d_spread_t = lambda * spread_{t-1} + c`` and converts
    the decay coefficient to a half-life. Returns ``inf`` when the spread shows
    no mean reversion (``lambda >= 0``).
    """
    s = spread.dropna()
    if len(s) < 3:
        return float("inf")
    lagged = s.shift(1).dropna()
    delta = s.diff().dropna()
    lagged, delta = lagged.align(delta, join="inner")

    design = np.column_stack([lagged.to_numpy(), np.ones(len(lagged))])
    coeffs, *_ = np.linalg.lstsq(design, delta.to_numpy(), rcond=None)
    lam = coeffs[0]
    if lam >= 0:
        return float("inf")
    return float(-np.log(2.0) / np.log(1.0 + lam))


def cointegration_test(
    base: pd.Series, quote: pd.Series, base_name: str = "base", quote_name: str = "quote"
) -> CointegrationResult:
    """Engle-Granger cointegration test for one pair.

    Requires the optional ``statsmodels`` dependency.
    """
    try:
        from statsmodels.tsa.stattools import coint
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "cointegration_test requires the optional 'statsmodels' dependency: "
            "pip install statsmodels"
        ) from exc

    aligned = pd.concat([base, quote], axis=1).dropna()
    statistic, pvalue, _ = coint(
        np.log(aligned.iloc[:, 0]), np.log(aligned.iloc[:, 1])
    )
    spread = np.log(aligned.iloc[:, 0]) - np.log(aligned.iloc[:, 1])
    return CointegrationResult(
        base=base_name,
        quote=quote_name,
        pvalue=float(pvalue),
        statistic=float(statistic),
        half_life=half_life(spread),
    )


def find_cointegrated_pairs(
    prices: pd.DataFrame, pvalue_threshold: float = 0.05
) -> list[CointegrationResult]:
    """Screen every column pair in ``prices`` for cointegration.

    ``prices`` holds one price series per column. Returns the cointegrated
    pairs sorted by p-value (strongest evidence first).
    """
    results: list[CointegrationResult] = []
    for col_a, col_b in itertools.combinations(prices.columns, 2):
        result = cointegration_test(
            prices[col_a], prices[col_b], base_name=col_a, quote_name=col_b
        )
        if result.pvalue < pvalue_threshold:
            results.append(result)
    return sorted(results, key=lambda r: r.pvalue)
