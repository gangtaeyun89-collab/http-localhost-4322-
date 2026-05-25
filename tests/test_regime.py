"""Synthetic-data tests for the regime module.

We construct a known two-regime sequence and verify the HMM recovers it
within tolerance, that BOCPD spikes at the true change point, and that
the signal layer escalates HOLD -> TRIM -> REDUCE under sustained crisis
posterior.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_tool.regime import GaussianHMM, bocpd, build_features, generate_signals
from quant_tool.regime.bocpd import recent_change_prob


def _two_regime_returns(rng, T=800, switch=400):
    """Calm regime (low vol) -> crisis regime (negative mean, high vol)."""
    calm = rng.normal(0.0005, 0.01, size=switch)
    crisis = rng.normal(-0.003, 0.035, size=T - switch)
    return np.concatenate([calm, crisis])


def test_hmm_recovers_two_regimes():
    rng = np.random.default_rng(42)
    r = _two_regime_returns(rng)
    idx = pd.date_range("2020-01-01", periods=len(r), freq="B")
    close = pd.Series(np.exp(np.cumsum(r)) * 100, index=idx)

    feats = build_features(close, vol_window=20, dd_window=60)
    X = feats.to_numpy()
    Xs = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-9)

    model = GaussianHMM(n_states=2, random_state=0, n_iter=300).fit(Xs)
    crisis_state = int(model.order_states_by_return(Xs)[0])
    posterior = model.predict_proba(Xs)

    # Crisis posterior should dominate in the back third.
    tail = posterior[-200:, crisis_state].mean()
    assert tail > 0.7, f"crisis posterior in tail = {tail:.2f}"


def test_bocpd_fires_near_true_change_point():
    rng = np.random.default_rng(7)
    r = _two_regime_returns(rng, T=400, switch=200)
    R = bocpd((r - r.mean()) / r.std())
    cp = recent_change_prob(R, window=10)

    # Probability of a recent change point should jump materially after the break.
    pre = cp[180:200].mean()
    post = cp[200:240].max()
    assert post > pre + 0.2


def test_signal_escalates_on_sustained_crisis():
    idx = pd.date_range("2024-01-01", periods=20, freq="B")
    # Posterior: bull for the first 10 bars, crisis ramping after.
    crisis = np.concatenate([np.zeros(10), np.linspace(0.7, 0.95, 10)])
    posterior = pd.DataFrame(
        {0: 1.0 - crisis, 1: crisis}, index=idx
    )
    out = generate_signals(
        posterior, crisis_state=1, crisis_threshold=0.6, persistence=3,
        reduce_threshold=0.85,
    )
    actions = out["action"].tolist()
    assert actions[:10] == ["HOLD"] * 10
    assert "TRIM" in actions
    assert "REDUCE" in actions
    # Reduce must only appear after trim.
    first_trim = actions.index("TRIM")
    first_reduce = actions.index("REDUCE")
    assert first_reduce >= first_trim


def test_build_features_no_lookahead():
    idx = pd.date_range("2024-01-01", periods=100, freq="B")
    close = pd.Series(np.cumprod(1 + np.random.default_rng(0).normal(0, 0.01, 100)), index=idx)
    feats = build_features(close, vol_window=5, dd_window=10)
    # First few bars must be dropped due to rolling windows.
    assert feats.index[0] > close.index[0]
    # Drawdown must be <= 0 by definition.
    assert (feats["dd"] <= 1e-12).all()
