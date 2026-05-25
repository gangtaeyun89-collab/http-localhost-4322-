"""Gaussian Hidden Markov Model fit by Baum-Welch.

Self-contained numpy implementation -- avoids the ``hmmlearn`` dependency,
which is not always installable in restricted environments.  Supports
diagonal-covariance multivariate emissions so the model can consume a
feature vector ``(return, realized_vol, drawdown, ...)`` rather than
returns alone.

The model is intentionally small: K states (typically 2-3), full transition
matrix, Gaussian emissions.  Initialisation uses k-means on the feature
matrix -- this is the standard trick to escape the symmetric saddle that
random init falls into.

References
----------
Hamilton, J. D. (1989). A new approach to the economic analysis of
nonstationary time series and the business cycle. *Econometrica*, 57.

Rabiner, L. R. (1989). A tutorial on hidden Markov models and selected
applications in speech recognition. *Proceedings of the IEEE*, 77(2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class GaussianHMM:
    """Diagonal-covariance Gaussian HMM with K hidden states.

    Parameters
    ----------
    n_states:
        Number of hidden regimes.  Two states pick out bull vs crisis; three
        adds a chop / transition state which is usually more interpretable.
    n_iter:
        Maximum Baum-Welch iterations.
    tol:
        Convergence threshold on log-likelihood improvement.
    random_state:
        Seed for k-means initialisation.
    """

    n_states: int = 3
    n_iter: int = 200
    tol: float = 1e-4
    random_state: int = 0

    # Fitted parameters -- populated by ``fit``.
    start_prob_: np.ndarray = field(default=None, repr=False)
    trans_mat_: np.ndarray = field(default=None, repr=False)
    means_: np.ndarray = field(default=None, repr=False)
    vars_: np.ndarray = field(default=None, repr=False)
    log_likelihood_: float = field(default=np.nan, repr=False)

    # ------------------------------------------------------------------ fit
    def fit(self, X: np.ndarray) -> "GaussianHMM":
        """Fit by Baum-Welch.  ``X`` is shape ``(T, D)``."""
        X = np.atleast_2d(X).astype(float)
        if X.ndim == 1:
            X = X[:, None]
        T, D = X.shape
        K = self.n_states

        self._kmeans_init(X)

        prev_ll = -np.inf
        for _ in range(self.n_iter):
            log_emit = self._log_emission(X)            # (T, K)
            log_alpha, ll = self._forward(log_emit)
            log_beta = self._backward(log_emit)

            log_gamma = log_alpha + log_beta
            log_gamma -= _logsumexp(log_gamma, axis=1, keepdims=True)
            gamma = np.exp(log_gamma)                   # (T, K)

            # xi[t,i,j] = P(s_t=i, s_{t+1}=j | X)
            log_trans = np.log(self.trans_mat_ + 1e-300)
            log_xi = (
                log_alpha[:-1, :, None]
                + log_trans[None, :, :]
                + log_emit[1:, None, :]
                + log_beta[1:, None, :]
            )
            log_xi -= _logsumexp(
                log_xi.reshape(T - 1, -1), axis=1, keepdims=True
            )[:, :, None]
            xi = np.exp(log_xi)

            # M-step
            self.start_prob_ = gamma[0] / gamma[0].sum()
            trans_num = xi.sum(axis=0)
            self.trans_mat_ = trans_num / trans_num.sum(axis=1, keepdims=True)

            gamma_sum = gamma.sum(axis=0)               # (K,)
            self.means_ = (gamma.T @ X) / gamma_sum[:, None]
            diff = X[:, None, :] - self.means_[None, :, :]    # (T, K, D)
            self.vars_ = (
                np.einsum("tk,tkd->kd", gamma, diff ** 2) / gamma_sum[:, None]
            )
            self.vars_ = np.maximum(self.vars_, 1e-6)

            if ll - prev_ll < self.tol:
                break
            prev_ll = ll

        self.log_likelihood_ = ll
        return self

    # ----------------------------------------------------------- inference
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Smoothed posterior P(state_t | X) -- shape ``(T, K)``."""
        X = np.atleast_2d(X).astype(float)
        log_emit = self._log_emission(X)
        log_alpha, _ = self._forward(log_emit)
        log_beta = self._backward(log_emit)
        log_gamma = log_alpha + log_beta
        log_gamma -= _logsumexp(log_gamma, axis=1, keepdims=True)
        return np.exp(log_gamma)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Viterbi MAP state sequence."""
        X = np.atleast_2d(X).astype(float)
        log_emit = self._log_emission(X)
        T, K = log_emit.shape
        log_trans = np.log(self.trans_mat_ + 1e-300)
        log_start = np.log(self.start_prob_ + 1e-300)

        delta = np.full((T, K), -np.inf)
        psi = np.zeros((T, K), dtype=int)
        delta[0] = log_start + log_emit[0]
        for t in range(1, T):
            scores = delta[t - 1, :, None] + log_trans
            psi[t] = np.argmax(scores, axis=0)
            delta[t] = scores[psi[t], np.arange(K)] + log_emit[t]

        path = np.zeros(T, dtype=int)
        path[-1] = int(np.argmax(delta[-1]))
        for t in range(T - 2, -1, -1):
            path[t] = psi[t + 1, path[t + 1]]
        return path

    def order_states_by_return(self, X: np.ndarray) -> np.ndarray:
        """Return state indices sorted from worst to best mean return.

        Convention: feature column 0 is the per-bar return.  Index ``0`` of
        the returned array is therefore the "crisis" regime and the last
        is "bull".  Saves the caller from rewiring colour maps every fit.
        """
        return np.argsort(self.means_[:, 0])

    # ------------------------------------------------------------ helpers
    def _kmeans_init(self, X: np.ndarray) -> None:
        rng = np.random.default_rng(self.random_state)
        K = self.n_states
        T, D = X.shape
        idx = rng.choice(T, size=K, replace=False)
        centers = X[idx].copy()
        for _ in range(20):
            d = ((X[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
            labels = np.argmin(d, axis=1)
            for k in range(K):
                mask = labels == k
                if mask.any():
                    centers[k] = X[mask].mean(axis=0)
        self.means_ = centers
        self.vars_ = np.tile(X.var(axis=0) + 1e-6, (K, 1))
        self.start_prob_ = np.full(K, 1.0 / K)
        self.trans_mat_ = np.full((K, K), 0.1 / (K - 1)) if K > 1 else np.ones((1, 1))
        if K > 1:
            np.fill_diagonal(self.trans_mat_, 0.9)

    def _log_emission(self, X: np.ndarray) -> np.ndarray:
        # log N(x | mu_k, diag(var_k)) summed over feature dims
        diff = X[:, None, :] - self.means_[None, :, :]
        log_norm = -0.5 * (
            np.log(2 * np.pi * self.vars_).sum(axis=1)[None, :]
            + (diff ** 2 / self.vars_[None, :, :]).sum(axis=2)
        )
        return log_norm

    def _forward(self, log_emit: np.ndarray) -> tuple[np.ndarray, float]:
        T, K = log_emit.shape
        log_trans = np.log(self.trans_mat_ + 1e-300)
        log_start = np.log(self.start_prob_ + 1e-300)
        log_alpha = np.empty_like(log_emit)
        log_alpha[0] = log_start + log_emit[0]
        for t in range(1, T):
            log_alpha[t] = (
                _logsumexp(log_alpha[t - 1, :, None] + log_trans, axis=0)
                + log_emit[t]
            )
        ll = float(_logsumexp(log_alpha[-1]))
        return log_alpha, ll

    def _backward(self, log_emit: np.ndarray) -> np.ndarray:
        T, K = log_emit.shape
        log_trans = np.log(self.trans_mat_ + 1e-300)
        log_beta = np.zeros_like(log_emit)
        for t in range(T - 2, -1, -1):
            log_beta[t] = _logsumexp(
                log_trans + (log_emit[t + 1] + log_beta[t + 1])[None, :],
                axis=1,
            )
        return log_beta


def _logsumexp(a: np.ndarray, axis=None, keepdims: bool = False) -> np.ndarray:
    a_max = np.max(a, axis=axis, keepdims=True)
    a_max = np.where(np.isfinite(a_max), a_max, 0.0)
    out = np.log(np.sum(np.exp(a - a_max), axis=axis, keepdims=keepdims))
    if not keepdims:
        a_max = np.squeeze(a_max, axis=axis)
    return out + a_max
