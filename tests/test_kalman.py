"""Tests for the Kalman dynamic hedge filter."""

import numpy as np
import pytest

from quant_tool.ai.kalman_filter import KalmanHedge
from quant_tool.data.ingestion import generate_cointegrated_pair


def test_recovers_true_hedge_ratio():
    """On a synthetic pair with a known beta, the filter should converge to it."""
    true_beta = 0.8
    prices = generate_cointegrated_pair(n=3000, beta=true_beta, seed=1)
    result = KalmanHedge(delta=1e-4).run(prices["base"], prices["quote"])

    # Once the filter has burned in, the estimate should sit near the truth.
    settled = result.beta.iloc[500:]
    assert abs(settled.mean() - true_beta) < 0.1


def test_output_shapes_and_index():
    prices = generate_cointegrated_pair(n=500, seed=2)
    result = KalmanHedge().run(prices["base"], prices["quote"])

    for series in (result.beta, result.alpha, result.spread, result.zscore):
        assert len(series) == len(prices)
        assert series.index.equals(prices.index)
    assert np.isfinite(result.innovation_std.to_numpy()).all()
    assert (result.innovation_std > 0).all()


def test_is_causal_truncation_invariant():
    """Bar t's estimate must not depend on data after t."""
    prices = generate_cointegrated_pair(n=1000, seed=3)
    full = KalmanHedge().run(prices["base"], prices["quote"])
    prefix = KalmanHedge().run(prices["base"].iloc[:600], prices["quote"].iloc[:600])

    np.testing.assert_allclose(
        full.beta.iloc[:600].to_numpy(), prefix.beta.to_numpy(), rtol=1e-10
    )


def test_rejects_bad_parameters():
    with pytest.raises(ValueError):
        KalmanHedge(delta=0.0)
    with pytest.raises(ValueError):
        KalmanHedge(obs_cov=-1.0)
