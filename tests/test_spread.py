"""Tests for hedge-ratio estimation and spread construction."""

import numpy as np
import pytest

from quant_tool.data.ingestion import generate_cointegrated_pair
from quant_tool.strategy.spread import (
    estimate_hedge,
    ols_hedge_ratio,
    rolling_ols_hedge,
)


def test_ols_recovers_true_beta():
    prices = generate_cointegrated_pair(n=3000, beta=0.8, alpha=1.5, seed=4)
    beta, alpha = ols_hedge_ratio(prices["base"], prices["quote"])
    assert abs(beta - 0.8) < 0.1
    assert abs(alpha - 1.5) < 0.5


def test_rolling_ols_warmup_is_nan():
    prices = generate_cointegrated_pair(n=300, seed=5)
    window = 60
    hedge = rolling_ols_hedge(prices["base"], prices["quote"], window)
    assert hedge["beta"].iloc[: window - 1].isna().all()
    assert hedge["beta"].iloc[window:].notna().all()


@pytest.mark.parametrize("method", ["ols", "kalman"])
def test_estimate_hedge_columns(method):
    prices = generate_cointegrated_pair(n=500, seed=6)
    frame = estimate_hedge(prices["base"], prices["quote"], method, zscore_lookback=60)
    assert list(frame.columns) == ["beta", "alpha", "spread", "zscore"]
    assert len(frame) == len(prices)


def test_estimate_hedge_rejects_unknown_method():
    prices = generate_cointegrated_pair(n=200, seed=7)
    with pytest.raises(ValueError):
        estimate_hedge(prices["base"], prices["quote"], "magic", zscore_lookback=60)


def test_zscore_is_roughly_standardised():
    """Away from warm-up the OLS z-score should be mean ~0, std ~1."""
    prices = generate_cointegrated_pair(n=3000, seed=8)
    frame = estimate_hedge(prices["base"], prices["quote"], "ols", zscore_lookback=60)
    z = frame["zscore"].dropna()
    assert abs(z.mean()) < 0.3
    assert abs(z.std() - 1.0) < 0.3
