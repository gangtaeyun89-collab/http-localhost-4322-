"""Turn regime posteriors into a discrete position-management signal.

For a concentrated long holding (the SK Hynix sell-timing case), the
useful output is not a buy/sell label but a *risk level*:

* HOLD       -- posterior is in the bull or normal regime
* TRIM       -- posterior on the crisis state has been elevated for a few
                bars, or BOCPD just fired a fresh change point
* REDUCE     -- crisis posterior is high *and* persistent

This module is intentionally rule-based and small: regime detection is
already noisy, and stacking another opaque classifier on top hides what
is actually driving the alert.

Nothing in this file is financial advice.  It is one input among many.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


HOLD = "HOLD"
TRIM = "TRIM"
REDUCE = "REDUCE"


@dataclass
class RegimeSignal:
    """Daily output bundle for the dashboard / log line."""

    date: pd.Timestamp
    regime: str            # human-readable label of the most likely state
    crisis_prob: float     # posterior mass on the worst-mean state
    cp_prob: float         # BOCPD recent change-point probability
    action: str            # HOLD / TRIM / REDUCE


def generate_signals(
    posterior: pd.DataFrame,
    crisis_state: int,
    cp_prob: pd.Series | None = None,
    crisis_threshold: float = 0.6,
    persistence: int = 3,
    reduce_threshold: float = 0.85,
    cp_threshold: float = 0.5,
) -> pd.DataFrame:
    """Combine HMM posterior and (optional) BOCPD output into actions.

    Parameters
    ----------
    posterior:
        ``(T, K)`` HMM posterior, datetime-indexed.  Columns are state ids.
    crisis_state:
        Column id of the worst-mean state, e.g. from
        :meth:`GaussianHMM.order_states_by_return`.
    cp_prob:
        Optional BOCPD recent-change-point probability series, same index
        as ``posterior``.
    crisis_threshold:
        Posterior on the crisis state above which we start *considering*
        trimming.
    persistence:
        Number of consecutive bars the crisis threshold must be exceeded
        before a TRIM is emitted -- damps single-day noise.
    reduce_threshold:
        Posterior level that escalates TRIM to REDUCE.
    cp_threshold:
        BOCPD probability above which the tripwire fires.  Treated as an
        independent route to TRIM so a fresh change point is not missed
        while the HMM is still smoothing.
    """
    crisis = posterior.iloc[:, crisis_state].astype(float)
    cp = cp_prob.reindex(posterior.index).fillna(0.0) if cp_prob is not None else pd.Series(0.0, index=posterior.index)

    above = crisis >= crisis_threshold
    run = above.rolling(persistence).sum().fillna(0)
    persistent = run >= persistence

    reduce_mask = (crisis >= reduce_threshold) & persistent
    trim_mask = persistent | (cp >= cp_threshold)

    action = pd.Series(HOLD, index=posterior.index)
    action[trim_mask] = TRIM
    action[reduce_mask] = REDUCE

    labels = posterior.idxmax(axis=1).astype(int)
    regime_names = {i: f"state_{i}" for i in posterior.columns.astype(int)}
    regime_names[crisis_state] = "crisis"

    out = pd.DataFrame(
        {
            "regime": labels.map(regime_names),
            "crisis_prob": crisis,
            "cp_prob": cp,
            "action": action,
        }
    )
    return out


def latest(signal_df: pd.DataFrame) -> RegimeSignal:
    """Return the most recent row as a structured signal."""
    row = signal_df.iloc[-1]
    return RegimeSignal(
        date=signal_df.index[-1],
        regime=str(row["regime"]),
        crisis_prob=float(row["crisis_prob"]),
        cp_prob=float(row["cp_prob"]),
        action=str(row["action"]),
    )
