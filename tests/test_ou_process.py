"""Tests for Ornstein-Uhlenbeck process estimation."""

import numpy as np
import pandas as pd

from quant_tool.strategy.ou_process import fit_ou_process


def _ou_series(n: int, b: float, sigma: float = 0.1, mu: float = 0.0, seed: int = 0):
    """Generate an AR(1) / discrete-OU series with a known decay ``b``."""
    rng = np.random.default_rng(seed)
    x = np.empty(n)
    x[0] = mu
    a = mu * (1.0 - b)
    shocks = rng.normal(0.0, sigma, n)
    for t in range(1, n):
        x[t] = a + b * x[t - 1] + shocks[t]
    return pd.Series(x)


def test_recovers_known_half_life():
    b = 0.95
    true_half_life = np.log(2.0) / -np.log(b)
    ou = fit_ou_process(_ou_series(20_000, b=b, seed=1))
    assert ou.is_tradable(max_half_life=50.0)
    assert abs(ou.half_life - true_half_life) / true_half_life < 0.15


def test_recovers_long_run_mean():
    ou = fit_ou_process(_ou_series(20_000, b=0.9, mu=5.0, seed=2))
    assert abs(ou.mu - 5.0) < 0.3


def test_random_walk_has_no_tradable_half_life():
    """A random walk fits an AR(1) coefficient near 1, so its half-life is
    either infinite or far too long to trade -- never a short, tradable one."""
    rng = np.random.default_rng(3)
    walk = pd.Series(np.cumsum(rng.normal(size=5_000)))
    ou = fit_ou_process(walk)
    assert not ou.is_tradable(max_half_life=100.0)
    assert ou.half_life > 100.0


def test_equilibrium_std_matches_sample_std():
    series = _ou_series(40_000, b=0.9, sigma=0.1, seed=4)
    ou = fit_ou_process(series)
    assert abs(ou.equilibrium_std - series.std()) / series.std() < 0.1


def test_short_series_is_non_reverting():
    ou = fit_ou_process(pd.Series([1.0, 2.0]))
    assert ou.half_life == float("inf")
    assert not ou.is_tradable(max_half_life=1_000.0)
