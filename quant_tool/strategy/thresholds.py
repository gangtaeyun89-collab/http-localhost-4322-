"""Optimal entry threshold for an Ornstein-Uhlenbeck spread.

Entering at a fixed +/-2 z-score is a rule of thumb. Bertram (2010) showed the
genuinely optimal threshold for an OU process maximises expected return per
unit time and depends on the mean-reversion speed and the transaction cost --
for cost-heavy crypto the optimum is usually tighter than 2.

Rather than evaluate Bertram's infinite-series first-passage formula (whose
constants are easy to get subtly wrong), this module computes the same
objective directly and verifiably: it simulates the fitted OU process and
measures the realised return-per-bar of an "enter at +/-a, exit at the mean"
rule across a grid of thresholds. The result is a principled, model-derived
threshold -- and, unlike a backtest grid search, it never touches strategy
P&L, so it does not overfit (the failure mode the walk-forward analysis
exposed).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from quant_tool.strategy.ou_process import OUParams


@dataclass(frozen=True)
class ThresholdResult:
    """Output of :func:`optimal_entry_threshold`.

    entry_threshold          best entry threshold (equilibrium-std units)
    expected_return_per_bar  the objective value achieved at that threshold
    expected_holding_bars    mean bars a position is held at that threshold
    """

    entry_threshold: float
    expected_return_per_bar: float
    expected_holding_bars: float


def _simulate_ou(theta: float, n: int, seed: int) -> np.ndarray:
    """Simulate a standardised OU path (equilibrium std = 1) in bar units."""
    phi = np.exp(-theta)
    shock_std = np.sqrt(1.0 - phi * phi)
    rng = np.random.default_rng(seed)
    shocks = rng.normal(0.0, shock_std, size=n)
    z = np.zeros(n)
    for t in range(1, n):
        z[t] = phi * z[t - 1] + shocks[t]
    return z


def _evaluate_threshold(
    z: np.ndarray, threshold: float, cost: float
) -> tuple[float, int, int]:
    """Net profit, trade count and held bars for an enter-/exit-at-mean rule."""
    position = 0
    entry_level = 0.0
    total_profit = 0.0
    n_trades = 0
    held_bars = 0
    for value in z:
        if position == 0:
            if value >= threshold:
                position, entry_level = -1, value  # short the spread
            elif value <= -threshold:
                position, entry_level = 1, value  # long the spread
        elif position == -1:  # opened high, exit at or below the mean
            held_bars += 1
            if value <= 0.0:
                total_profit += (entry_level - value) - cost
                n_trades += 1
                position = 0
        else:  # position == 1; opened low, exit at or above the mean
            held_bars += 1
            if value >= 0.0:
                total_profit += (value - entry_level) - cost
                n_trades += 1
                position = 0
    return total_profit, n_trades, held_bars


def optimal_entry_threshold(
    ou: OUParams,
    cost: float,
    candidate_thresholds: np.ndarray | None = None,
    sim_length: int = 150_000,
    seed: int = 0,
) -> ThresholdResult:
    """Find the entry threshold that maximises expected return per unit time.

    Parameters
    ----------
    ou:
        Fitted OU parameters of the spread; only ``theta`` is used. The process
        must be mean-reverting (``theta > 0``).
    cost:
        Round-trip transaction cost in the same equilibrium-std ("z-score")
        units as the threshold. Larger cost pushes the optimum wider.
    candidate_thresholds:
        Thresholds to evaluate; defaults to a sweep of ``[0.5, 3.5]``.
    sim_length, seed:
        Length and seed of the simulated OU path; fixed seed keeps the result
        deterministic.
    """
    if ou.theta <= 0.0:
        raise ValueError("OU process is not mean-reverting (theta <= 0)")
    if cost < 0.0:
        raise ValueError("cost must be non-negative")
    if candidate_thresholds is None:
        candidate_thresholds = np.linspace(0.5, 3.5, 16)

    z = _simulate_ou(ou.theta, sim_length, seed)

    best = ThresholdResult(float(candidate_thresholds[0]), float("-inf"), 0.0)
    for threshold in candidate_thresholds:
        profit, n_trades, held = _evaluate_threshold(z, float(threshold), cost)
        return_per_bar = profit / sim_length
        if return_per_bar > best.expected_return_per_bar:
            best = ThresholdResult(
                entry_threshold=float(threshold),
                expected_return_per_bar=float(return_per_bar),
                expected_holding_bars=float(held / n_trades) if n_trades else 0.0,
            )
    return best
