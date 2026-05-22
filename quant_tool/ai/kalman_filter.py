"""Dynamic hedge-ratio estimation with a Kalman filter.

This is the highest-impact "AI" component for crypto pairs trading. The
relationship between two assets drifts quickly, so a static OLS hedge ratio
decays and the spread stops being mean-reverting. The Kalman filter treats the
hedge ratio as a latent state that evolves as a random walk and re-estimates it
every bar.

State-space model (one observation per bar)::

    state    x_t  = [beta_t, alpha_t]      (random walk:  x_t = x_{t-1} + w_t)
    observ.  y_t  = H_t . x_t + v_t        with  H_t = [log_quote_t, 1]

where ``y_t = log_base_t``. Two quantities fall out of the recursion for free:

* the innovation ``e_t`` -- the part of ``y_t`` not explained by the current
  hedge -- which *is* the tradable spread; and
* its variance ``Q_t``, so ``e_t / sqrt(Q_t)`` is a self-normalising z-score
  that needs no separate rolling window.

The filter is strictly causal: the estimate at bar ``t`` uses only data up to
and including ``t``, so feeding it into a backtest introduces no look-ahead.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class KalmanResult:
    """Per-bar output of :meth:`KalmanHedge.run`.

    All series share the input index.

    beta            filtered hedge ratio
    alpha           filtered intercept
    spread          innovation e_t -- the tradable, hedge-adjusted residual
    innovation_std  sqrt(Q_t), the predicted standard deviation of ``spread``
    zscore          spread / innovation_std, a self-normalising signal
    """

    beta: pd.Series
    alpha: pd.Series
    spread: pd.Series
    innovation_std: pd.Series
    zscore: pd.Series

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "beta": self.beta,
                "alpha": self.alpha,
                "spread": self.spread,
                "innovation_std": self.innovation_std,
                "zscore": self.zscore,
            }
        )


class KalmanHedge:
    """Kalman filter that tracks a time-varying ``[beta, alpha]`` hedge.

    The transition covariance is diagonal, ``diag(q_beta, q_alpha)``, so the
    hedge slope and the intercept can drift on different timescales. This
    matters: if the intercept is allowed to move quickly it tracks (and erases)
    the spread's own mean reversion -- the very signal the strategy trades.

    Parameters
    ----------
    delta:
        Sets the slope process variance ``q_beta = delta / (1 - delta)`` and so
        how fast the hedge ratio adapts. It must stay small enough to track only
        slow hedge drift, not the fast mean reversion of the spread. ``1e-7``
        separates those timescales well for hourly crypto data; larger values
        progressively whiten the spread.
    obs_cov:
        Observation noise variance ``R``. Scales the innovation variance and
        therefore the filter's native z-score.
    alpha_ratio:
        Intercept process variance as a fraction of ``q_beta``. Keep it small so
        the intercept settles and stays put; ``0`` freezes it entirely once
        converged, recovering the textbook slope-only pairs filter.
    """

    def __init__(
        self,
        delta: float = 1e-7,
        obs_cov: float = 1e-3,
        alpha_ratio: float = 0.01,
    ) -> None:
        if not 0.0 < delta < 1.0:
            raise ValueError("delta must be in (0, 1)")
        if obs_cov <= 0.0:
            raise ValueError("obs_cov must be positive")
        if alpha_ratio < 0.0:
            raise ValueError("alpha_ratio must be non-negative")
        self.delta = delta
        self.obs_cov = obs_cov
        self.alpha_ratio = alpha_ratio

    def run(self, base: pd.Series, quote: pd.Series) -> KalmanResult:
        """Filter the pair and return per-bar hedge estimates.

        ``base`` is regressed on ``quote``; both are price levels and are
        log-transformed internally.
        """
        if len(base) != len(quote):
            raise ValueError("base and quote must have equal length")
        if not base.index.equals(quote.index):
            raise ValueError("base and quote must share the same index")
        if len(base) < 2:
            raise ValueError("need at least 2 observations")

        log_base = np.log(base.to_numpy(dtype=float))
        log_quote = np.log(quote.to_numpy(dtype=float))
        n = len(log_base)

        q_beta = self.delta / (1.0 - self.delta)
        trans_cov = np.diag([q_beta, q_beta * self.alpha_ratio])

        # State [beta, alpha] and its covariance. The prior is uninformative
        # (zero mean, unit variance). Because each bar supplies only one
        # observation for two states, beta needs a warm-up of a few hundred
        # bars to settle -- the backtest excludes that warm-up via the z-score
        # lookback, and callers should not trust the earliest estimates.
        state = np.zeros(2)
        cov = np.eye(2) * 1.0

        beta = np.empty(n)
        alpha = np.empty(n)
        spread = np.empty(n)
        innov_std = np.empty(n)

        for t in range(n):
            obs_matrix = np.array([log_quote[t], 1.0])

            # Predict: random-walk transition inflates the covariance.
            cov_pred = cov + trans_cov

            # Innovation: observed minus predicted log price of the base leg.
            prediction = obs_matrix @ state
            error = log_base[t] - prediction
            innov_var = obs_matrix @ cov_pred @ obs_matrix + self.obs_cov

            # Update with the Kalman gain.
            gain = cov_pred @ obs_matrix / innov_var
            state = state + gain * error
            cov = cov_pred - np.outer(gain, obs_matrix) @ cov_pred

            beta[t] = state[0]
            alpha[t] = state[1]
            spread[t] = error
            innov_std[t] = np.sqrt(innov_var)

        index = base.index
        spread_s = pd.Series(spread, index=index, name="spread")
        innov_s = pd.Series(innov_std, index=index, name="innovation_std")
        return KalmanResult(
            beta=pd.Series(beta, index=index, name="beta"),
            alpha=pd.Series(alpha, index=index, name="alpha"),
            spread=spread_s,
            innovation_std=innov_s,
            zscore=(spread_s / innov_s).rename("zscore"),
        )
