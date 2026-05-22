"""Tests for cointegration screening and half-life estimation."""

import numpy as np
import pandas as pd

from quant_tool.data.ingestion import generate_cointegrated_pair
from quant_tool.strategy.pair_finder import cointegration_test, half_life


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
