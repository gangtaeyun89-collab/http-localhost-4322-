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

from quant_tool.strategy.ou_process import fit_ou_process
from quant_tool.strategy.spread import ols_hedge_ratio


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

    A thin wrapper over :func:`~quant_tool.strategy.ou_process.fit_ou_process`;
    returns ``inf`` when the spread shows no mean reversion.
    """
    return fit_ou_process(spread).half_life


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
    log_base = np.log(aligned.iloc[:, 0])
    log_quote = np.log(aligned.iloc[:, 1])
    statistic, pvalue, _ = coint(log_base, log_quote)

    # The half-life must be measured on the *cointegrating* residual, not on a
    # raw log-ratio: with a hedge ratio far from 1.0 the ratio keeps a
    # non-stationary component and the half-life is badly inflated. Estimate
    # the hedge ratio (the Engle-Granger first stage) and use that spread.
    beta, alpha = ols_hedge_ratio(aligned.iloc[:, 0], aligned.iloc[:, 1])
    spread = log_base - beta * log_quote - alpha
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
    pairs sorted by p-value (strongest evidence first). A pair whose test fails
    on degenerate input (zero variance, too short) is skipped rather than
    aborting the whole screen.
    """
    results: list[CointegrationResult] = []
    for col_a, col_b in itertools.combinations(prices.columns, 2):
        try:
            result = cointegration_test(
                prices[col_a], prices[col_b], base_name=col_a, quote_name=col_b
            )
        except ImportError:
            raise  # missing statsmodels is a setup error, not a bad pair
        except Exception:
            continue  # degenerate pair: skip, keep screening the rest
        if result.pvalue < pvalue_threshold:
            results.append(result)
    return sorted(results, key=lambda r: r.pvalue)


def rolling_cointegration(
    base: pd.Series,
    quote: pd.Series,
    window: int,
    step: int | None = None,
) -> pd.DataFrame:
    """Re-test cointegration on a rolling window.

    Cointegration in crypto decays fast: a pair that is stationary over a long
    sample can be dead in the last month. This slides a ``window``-bar window
    forward in ``step`` increments and re-runs the Engle-Granger test, so the
    *persistence* of the relationship is visible -- not just one full-sample
    verdict.

    Returns a DataFrame indexed by each window's end timestamp, with columns
    ``pvalue``, ``half_life`` and ``is_cointegrated``. ``step`` defaults to a
    quarter of the window; a very small ``step`` is accurate but slow.
    """
    aligned = pd.concat([base, quote], axis=1).dropna()
    if window < 20:
        raise ValueError("window must be >= 20 bars")
    if window > len(aligned):
        raise ValueError(f"window {window} exceeds the {len(aligned)} aligned bars")
    if step is None:
        step = max(1, window // 4)
    if step < 1:
        raise ValueError("step must be >= 1")

    records: list[tuple[float, float, bool]] = []
    index: list = []
    for end in range(window, len(aligned) + 1, step):
        window_slice = aligned.iloc[end - window : end]
        result = cointegration_test(window_slice.iloc[:, 0], window_slice.iloc[:, 1])
        records.append((result.pvalue, result.half_life, result.is_cointegrated))
        index.append(aligned.index[end - 1])

    return pd.DataFrame(
        records, index=index, columns=["pvalue", "half_life", "is_cointegrated"]
    )
