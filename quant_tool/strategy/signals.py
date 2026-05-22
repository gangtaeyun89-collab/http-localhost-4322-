"""Signal generation: turn a spread z-score into target spread positions.

The output is a series of *target* positions in ``{-1, 0, +1}`` where ``+1``
means long the spread (long base, short ``beta`` * quote). The backtest engine
is responsible for applying the standard one-bar execution lag, so this module
stays free of any timing assumptions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_tool.config.settings import SignalConfig


def generate_positions(zscore: pd.Series, config: SignalConfig) -> pd.Series:
    """Run the mean-reversion state machine over a z-score series.

    Logic, per bar:

    * flat and ``z >= entry_z``      -> short the spread (-1)
    * flat and ``z <= -entry_z``     -> long the spread (+1)
    * in a position, z back inside the ``exit_z`` band -> close (0)
    * in a position, z past ``stop_z`` the wrong way   -> stop out (0)

    A NaN z-score (warm-up, or a degenerate zero-variance window) is treated as
    "no information": the current position is held and no new trade is opened.
    """
    z = zscore.to_numpy(dtype=float)
    positions = np.zeros(len(z), dtype=int)
    pos = 0

    for t, zt in enumerate(z):
        if np.isnan(zt):
            positions[t] = pos
            continue

        if pos == 0:
            if zt >= config.entry_z:
                pos = -1
            elif zt <= -config.entry_z:
                pos = 1
        elif pos == 1:  # long the spread; opened when z was very negative
            if zt >= -config.exit_z or zt <= -config.stop_z:
                pos = 0
        else:  # pos == -1; short the spread; opened when z was very positive
            if zt <= config.exit_z or zt >= config.stop_z:
                pos = 0

        positions[t] = pos

    return pd.Series(positions, index=zscore.index, name="position")
