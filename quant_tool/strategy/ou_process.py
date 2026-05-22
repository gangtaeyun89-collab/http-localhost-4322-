"""Ornstein-Uhlenbeck process estimation for a mean-reverting spread.

The OU process is the canonical model for a tradable spread:

    dX_t = theta * (mu - X_t) dt + sigma dW_t

Its exact discrete-time form is an AR(1), ``X_t = a + b * X_{t-1} + eps`` with
``b = exp(-theta)``, so the parameters are recovered by a single OLS fit.

The number that matters most for trading is the **half-life** ``ln(2)/theta`` --
the expected time for the spread to revert halfway to its mean. If the
half-life exceeds the holding period you can tolerate, the pair is not
tradable, however cleanly it cointegrates.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

_INF = float("inf")


@dataclass(frozen=True)
class OUParams:
    """Fitted Ornstein-Uhlenbeck parameters (all times in bars).

    theta            mean-reversion speed; 0 when the series is not reverting
    mu               long-run mean the process reverts to
    sigma            instantaneous volatility of the driving noise
    half_life        ln(2) / theta -- bars to revert halfway (inf if not reverting)
    equilibrium_std  stationary standard deviation of the process (inf if not)
    """

    theta: float
    mu: float
    sigma: float
    half_life: float
    equilibrium_std: float

    def is_tradable(self, max_half_life: float) -> bool:
        """True when the spread reverts fast enough to be worth trading.

        A point estimate of the AR(1) coefficient cannot by itself tell a slow
        mean-reverter apart from a random walk -- that is the cointegration /
        unit-root test's job (a finite sample of a random walk fits ``b`` just
        below 1). What this *can* answer is the methodology's practical gate:
        is the estimated half-life short enough to act on?
        """
        return self.half_life <= max_half_life


def fit_ou_process(series: pd.Series) -> OUParams:
    """Fit an Ornstein-Uhlenbeck process to ``series`` via its AR(1) form.

    Estimates ``X_t = a + b * X_{t-1} + eps`` by OLS. Mean reversion requires
    ``0 < b < 1``; outside that range the series is a random walk (``b >= 1``)
    or oscillatory/degenerate (``b <= 0``) and is reported as non-reverting
    (``half_life = inf``) so callers uniformly reject it.
    """
    s = series.dropna()
    if len(s) < 3:
        mean = float(s.mean()) if len(s) else 0.0
        return OUParams(0.0, mean, 0.0, _INF, _INF)

    x_prev = s.to_numpy()[:-1]
    x_curr = s.to_numpy()[1:]
    design = np.column_stack([x_prev, np.ones(len(x_prev))])
    (b, a), *_ = np.linalg.lstsq(design, x_curr, rcond=None)

    residuals = x_curr - (a + b * x_prev)
    # Two parameters (a, b) were estimated, hence ddof=2.
    sigma_eps = float(np.std(residuals, ddof=2)) if len(residuals) > 2 else 0.0

    if not 0.0 < b < 1.0:
        return OUParams(
            theta=0.0, mu=float(s.mean()), sigma=0.0,
            half_life=_INF, equilibrium_std=_INF,
        )

    theta = float(-np.log(b))
    mu = float(a / (1.0 - b))
    one_minus_b2 = 1.0 - b * b
    sigma = float(sigma_eps * np.sqrt(2.0 * theta / one_minus_b2))
    half_life = float(np.log(2.0) / theta)
    equilibrium_std = float(sigma_eps / np.sqrt(one_minus_b2))
    return OUParams(
        theta=theta, mu=mu, sigma=sigma,
        half_life=half_life, equilibrium_std=equilibrium_std,
    )
