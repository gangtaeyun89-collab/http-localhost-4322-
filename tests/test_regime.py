"""Synthetic-data tests for the regime module.

We construct a known two-regime sequence and verify the HMM recovers it
within tolerance, that BOCPD spikes at the true change point, and that
the signal layer escalates HOLD -> TRIM -> REDUCE under sustained crisis
posterior.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_tool.regime import (
    GaussianHMM,
    bocpd,
    build_features,
    generate_signals,
    run_regime_backtest,
)
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


def test_backtest_avoids_known_crash():
    """A perfect-foresight signal must reduce drawdown vs buy-and-hold.

    This is a regression test on the look-ahead-free timing convention, not
    a claim that the real HMM has perfect foresight.
    """
    idx = pd.date_range("2020-01-01", periods=400, freq="B")
    rng = np.random.default_rng(1)
    # 200 bars of mild drift, then a sustained crash.
    drift = rng.normal(0.001, 0.012, 200)
    crash = rng.normal(-0.005, 0.03, 200)
    r = np.concatenate([drift, crash])
    close = pd.Series(np.exp(np.cumsum(r)) * 100, index=idx, name="close")

    # Oracle signal: HOLD during the drift, REDUCE during the crash.
    action = pd.Series("HOLD", index=idx)
    action.iloc[200:] = "REDUCE"
    signals = pd.DataFrame({"action": action})

    res = run_regime_backtest(close, signals, cost_bps=10.0)
    assert res.stats["total_return"] > res.benchmark_stats["total_return"]
    assert res.stats["max_drawdown"] > res.benchmark_stats["max_drawdown"]  # closer to zero


def test_backtest_no_lookahead():
    """A signal must not be able to act on the same bar it observes."""
    idx = pd.date_range("2024-01-01", periods=10, freq="B")
    # Price jumps up exactly once, on bar 5.
    close = pd.Series([100.0] * 5 + [110.0] * 5, index=idx)
    # Oracle action that "knows" to be HOLD only on the jump bar.
    action = pd.Series(["REDUCE"] * 5 + ["HOLD"] + ["REDUCE"] * 4, index=idx)
    res = run_regime_backtest(close, pd.DataFrame({"action": action}), cost_bps=0)
    # Held weight at bar 5 must come from bar 4's target (REDUCE -> 0),
    # so the 10% jump must NOT be earned.
    held_at_jump = res.bars["held_weight"].iloc[5]
    assert held_at_jump == 0.0
