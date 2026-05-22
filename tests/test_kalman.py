"""Tests for the Kalman dynamic hedge filter."""

import numpy as np
import pandas as pd
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


def test_rejects_misaligned_index():
    """Equal-length but index-misaligned series would zip by position and
    silently produce a wrong hedge ratio -- the filter must reject them."""
    base = pd.Series([10.0, 11.0, 12.0], index=[0, 1, 2])
    quote = pd.Series([5.0, 5.5, 6.0], index=[100, 101, 102])
    with pytest.raises(ValueError):
        KalmanHedge().run(base, quote)


def test_log_likelihood_is_finite():
    prices = generate_cointegrated_pair(n=800, seed=40)
    result = KalmanHedge().run(prices["base"], prices["quote"])
    assert np.isfinite(result.log_likelihood)


def test_fit_beats_hand_picked_extremes():
    """The maximum-likelihood delta must outscore deliberately bad values."""
    prices = generate_cointegrated_pair(n=2000, beta_drift_vol=0.001, seed=41)
    base, quote = prices["base"], prices["quote"]

    fitted = KalmanHedge.fit(base, quote)
    fitted_ll = fitted.run(base, quote).log_likelihood
    too_slow = KalmanHedge(delta=1e-9).run(base, quote).log_likelihood
    too_fast = KalmanHedge(delta=1e-2).run(base, quote).log_likelihood

    assert fitted_ll > too_slow
    assert fitted_ll > too_fast
    assert 0.0 < fitted.delta < 1.0


def test_fit_adapts_delta_to_drift():
    """A faster-drifting hedge ratio should call for a faster-adapting filter."""
    static = generate_cointegrated_pair(n=3000, beta_drift_vol=0.0, seed=42)
    drifting = generate_cointegrated_pair(n=3000, beta_drift_vol=0.003, seed=42)

    static_fit = KalmanHedge.fit(static["base"], static["quote"])
    drifting_fit = KalmanHedge.fit(drifting["base"], drifting["quote"])
    assert drifting_fit.delta >= static_fit.delta
