"""Tests for the mean-reversion signal state machine."""

import numpy as np
import pandas as pd

from quant_tool.config.settings import SignalConfig
from quant_tool.strategy.signals import generate_positions

CONFIG = SignalConfig(zscore_lookback=10, entry_z=2.0, exit_z=0.5, stop_z=4.0)


def test_entry_exit_cycle():
    z = pd.Series([0.0, 1.0, 2.5, 1.0, 0.3, -1.0, -2.5, -0.2, 0.0, 4.5])
    positions = generate_positions(z, CONFIG)
    expected = [0, 0, -1, -1, 0, 0, 1, 0, 0, -1]
    assert positions.tolist() == expected


def test_stop_loss_flattens_position():
    """A short spread that keeps diverging past stop_z must be cut."""
    z = pd.Series([0.0, 2.5, 3.0, 4.5, 1.5])
    positions = generate_positions(z, CONFIG)
    # enter short at z=2.5, stopped out when z hits 4.5, stays flat after
    # (z=1.5 is below entry_z so no re-entry).
    assert positions.tolist() == [0, -1, -1, 0, 0]


def test_reentry_after_stop_when_signal_still_extreme():
    """After a stop-out the state machine re-enters if z is still past entry_z."""
    z = pd.Series([0.0, 2.5, 4.5, 3.0])
    positions = generate_positions(z, CONFIG)
    assert positions.tolist() == [0, -1, 0, -1]


def test_nan_holds_current_position():
    z = pd.Series([0.0, 2.5, np.nan, 0.3])
    positions = generate_positions(z, CONFIG)
    assert positions.tolist() == [0, -1, -1, 0]


def test_no_signal_when_threshold_unreached():
    z = pd.Series([0.5, -0.5, 1.9, -1.9, 0.0])
    positions = generate_positions(z, CONFIG)
    assert positions.tolist() == [0, 0, 0, 0, 0]
