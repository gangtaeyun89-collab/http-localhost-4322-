"""Tests for the OU-derived optimal entry threshold."""

import numpy as np
import pytest

from quant_tool.strategy.ou_process import OUParams
from quant_tool.strategy.thresholds import optimal_entry_threshold

# A mean-reverting OU with a ~30-bar half-life.
_OU = OUParams(
    theta=float(np.log(2.0) / 30.0),
    mu=0.0,
    sigma=0.1,
    half_life=30.0,
    equilibrium_std=1.0,
)


def test_optimal_threshold_rises_with_transaction_cost():
    """Higher cost requires a larger move to be worth trading."""
    cheap = optimal_entry_threshold(_OU, cost=0.0, sim_length=60_000, seed=1)
    pricey = optimal_entry_threshold(_OU, cost=1.0, sim_length=60_000, seed=1)
    assert pricey.entry_threshold > cheap.entry_threshold


def test_optimal_threshold_stays_in_candidate_range():
    result = optimal_entry_threshold(_OU, cost=0.3, sim_length=60_000, seed=2)
    assert 0.5 <= result.entry_threshold <= 3.5
    assert result.expected_holding_bars > 0.0


def test_rejects_non_mean_reverting_process():
    flat = OUParams(theta=0.0, mu=0.0, sigma=0.0, half_life=float("inf"),
                    equilibrium_std=float("inf"))
    with pytest.raises(ValueError):
        optimal_entry_threshold(flat, cost=0.1)


def test_rejects_negative_cost():
    with pytest.raises(ValueError):
        optimal_entry_threshold(_OU, cost=-0.1, sim_length=10_000)
