"""Feature engineering for regime detection.

Stylised facts of Korean single-name equities -- fat tails, volatility
clustering, asymmetric drawdowns -- mean a 1-D return series throws away
most of the signal a regime model could exploit.  The default feature
vector is:

* log-return                                     (level)
* rolling realized volatility                     (dispersion)
* drawdown from trailing-N high                   (asymmetry)

All features are computed without look-ahead so the resulting matrix can
be fed directly to either the HMM or BOCPD.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_features(
    close: pd.Series,
    vol_window: int = 20,
    dd_window: int = 60,
) -> pd.DataFrame:
    """Construct the standard regime feature matrix from a close series.

    Parameters
    ----------
    close:
        Adjusted close price, datetime-indexed.
    vol_window:
        Rolling window for realized volatility (in bars).
    dd_window:
        Rolling window for the trailing-high used by the drawdown feature.

    Returns
    -------
    DataFrame with columns ``ret, rv, dd``; rows containing NaN from the
    warm-up period are dropped.
    """
    close = close.astype(float).sort_index()
    ret = np.log(close).diff()
    rv = ret.rolling(vol_window).std()
    rolling_high = close.rolling(dd_window, min_periods=1).max()
    dd = close / rolling_high - 1.0

    feats = pd.concat({"ret": ret, "rv": rv, "dd": dd}, axis=1).dropna()
    return feats
