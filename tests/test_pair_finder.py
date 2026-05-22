"""Tests for cointegration screening and half-life estimation."""

import numpy as np
import pandas as pd
import pytest

from quant_tool.data.ingestion import generate_cointegrated_pair
from quant_tool.strategy.pair_finder import (
    cointegration_test,
    half_life,
    rolling_cointegration,
)


def test_cointegration_detects_a_cointegrated_pair():
    prices = generate_cointegrated_pair(n=2500, beta=0.4, seed=20)
    result = cointegration_test(prices["base"], prices["quote"])
    assert result.is_cointegrated
    assert result.pvalue < 0.05


def test_half_life_uses_hedge_adjusted_spread():
    """Half-life must reflect the true OU process even when the hedge ratio is
    far from 1.0; a raw log(base)-log(quote) spread would inflate it badly."""
    prices = generate_cointegrated_pair(
        n=3000, beta=0.4, spread_halflife=20.0, seed=20
    )
    result = cointegration_test(prices["base"], prices["quote"])
    assert 8.0 < result.half_life < 45.0


def test_half_life_infinite_for_random_walk():
    """A non-mean-reverting series has no finite half-life."""
    rng = np.random.default_rng(0)
    walk = pd.Series(np.cumsum(rng.normal(size=2000)))
    assert half_life(walk) == float("inf") or half_life(walk) > 200


def test_rolling_cointegration_stable_pair_stays_cointegrated():
    # A fast-reverting spread and a window large vs the half-life, so the
    # Engle-Granger test genuinely has power within each window.
    prices = generate_cointegrated_pair(
        n=4000, beta_drift_vol=0.0, spread_halflife=15.0, seed=30
    )
    rolling = rolling_cointegration(prices["base"], prices["quote"], window=1200)
    assert list(rolling.columns) == ["pvalue", "half_life", "is_cointegrated"]
    assert rolling["is_cointegrated"].mean() > 0.7


def test_rolling_cointegration_random_walks_rarely_cointegrate():
    rng = np.random.default_rng(31)
    idx = pd.date_range("2023-01-01", periods=4000, freq="h", tz="UTC")
    a = pd.Series(100.0 + np.cumsum(rng.normal(size=4000)), index=idx)
    b = pd.Series(100.0 + np.cumsum(rng.normal(size=4000)), index=idx)
    rolling = rolling_cointegration(a, b, window=1200)
    assert rolling["is_cointegrated"].mean() < 0.3


def test_rolling_cointegration_rejects_oversized_window():
    prices = generate_cointegrated_pair(n=500, seed=32)
    with pytest.raises(ValueError):
        rolling_cointegration(prices["base"], prices["quote"], window=900)
