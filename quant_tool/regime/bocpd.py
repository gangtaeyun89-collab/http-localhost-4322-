"""Bayesian Online Change-Point Detection (Adams & MacKay, 2007).

Univariate Gaussian observation model with a Normal-Inverse-Gamma prior so
both the mean and variance of each "run" are integrated out -- the right
conjugate setup for return series where volatility shifts matter as much
as level shifts.

The output is a ``(T, T)`` lower-triangular run-length posterior; for a
trader's purposes the useful summary is the *probability that a change
point occurred in the last K bars*, which :func:`recent_change_prob`
extracts.

Reference
---------
Adams, R. P. and MacKay, D. J. C. (2007). Bayesian Online Changepoint
Detection. arXiv:0710.3742.
"""

from __future__ import annotations

import math

import numpy as np


def gammaln(x):
    """Element-wise log-gamma without forcing a scipy dependency."""
    return np.asarray(np.frompyfunc(math.lgamma, 1, 1)(x), dtype=float)


def bocpd(
    x: np.ndarray,
    hazard: float = 1 / 250,
    mu0: float = 0.0,
    kappa0: float = 0.1,
    alpha0: float = 1.0,
    beta0: float = 1.0,
) -> np.ndarray:
    """Run BOCPD over the 1-D series ``x``.

    Parameters
    ----------
    x:
        Observation series (typically standardised returns).
    hazard:
        Constant hazard rate.  ``1/250`` means a prior expectation of one
        change point per trading year.
    mu0, kappa0, alpha0, beta0:
        Normal-Inverse-Gamma hyperparameters.  Defaults are weak.

    Returns
    -------
    Lower-triangular ``(T, T)`` array where row ``t`` holds the posterior
    over run length at time ``t``.
    """
    x = np.asarray(x, dtype=float).ravel()
    T = len(x)
    R = np.zeros((T + 1, T + 1))
    R[0, 0] = 1.0

    mu = np.array([mu0])
    kappa = np.array([kappa0])
    alpha = np.array([alpha0])
    beta = np.array([beta0])

    for t in range(T):
        # Predictive: Student-t with df = 2*alpha, loc = mu, scale^2 = beta*(kappa+1)/(alpha*kappa)
        df = 2.0 * alpha
        scale2 = beta * (kappa + 1.0) / (alpha * kappa)
        pred = _student_t_logpdf(x[t], df, mu, np.sqrt(scale2))

        # Growth: run length grows by 1 with prob (1 - hazard)
        growth = R[t, : t + 1] * np.exp(pred) * (1.0 - hazard)
        # Change point: collapse to run length 0
        cp = (R[t, : t + 1] * np.exp(pred) * hazard).sum()

        R[t + 1, 0] = cp
        R[t + 1, 1 : t + 2] = growth
        R[t + 1] /= R[t + 1].sum() + 1e-300

        # Update sufficient stats for each surviving run length and prepend
        # the prior for the brand-new run length 0.
        kappa_new = kappa + 1.0
        mu_new = (kappa * mu + x[t]) / kappa_new
        alpha_new = alpha + 0.5
        beta_new = beta + 0.5 * kappa * (x[t] - mu) ** 2 / kappa_new

        mu = np.concatenate(([mu0], mu_new))
        kappa = np.concatenate(([kappa0], kappa_new))
        alpha = np.concatenate(([alpha0], alpha_new))
        beta = np.concatenate(([beta0], beta_new))

    return R[1:, :]


def recent_change_prob(R: np.ndarray, window: int = 5) -> np.ndarray:
    """Probability that a change-point occurred within the last ``window`` bars.

    Equivalent to summing posterior mass on run lengths shorter than
    ``window`` at each time step.
    """
    T = R.shape[0]
    out = np.zeros(T)
    for t in range(T):
        out[t] = R[t, : min(window, t + 1)].sum()
    return out


def _student_t_logpdf(
    x: float, df: np.ndarray, loc: np.ndarray, scale: np.ndarray
) -> np.ndarray:
    z = (x - loc) / scale
    return (
        gammaln((df + 1) / 2.0)
        - gammaln(df / 2.0)
        - 0.5 * np.log(df * np.pi)
        - np.log(scale)
        - (df + 1) / 2.0 * np.log1p(z ** 2 / df)
    )
