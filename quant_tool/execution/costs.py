"""Trading cost model.

In crypto mean-reversion, fees and slippage usually consume most of the gross
edge, so costs are modelled explicitly rather than bolted on as an afterthought.
All costs are expressed as a fraction of deployed (gross) capital so they can be
subtracted directly from the strategy's per-bar return.

The placeholder here uses fixed basis-point assumptions. It is the natural seam
for the ML execution model from the architecture: a learned ``slippage_bps``
predicted from order-book depth, recent volatility and order size can be swapped
in without touching the backtest engine.
"""

from __future__ import annotations

import pandas as pd

from quant_tool.config.settings import CostConfig


class CostModel:
    """Converts position changes and holdings into per-bar cost drag."""

    def __init__(self, config: CostConfig, bars_per_year: int) -> None:
        if bars_per_year <= 0:
            raise ValueError("bars_per_year must be positive")
        self.config = config
        self.bars_per_year = bars_per_year

    def trade_cost(self, positions: pd.Series) -> pd.Series:
        """Cost incurred when the position changes.

        Both legs trade together, so the cost of moving the spread position by
        ``d`` is ``|d| * cost_rate`` as a fraction of deployed capital. The very
        first bar's move counts as the cost of establishing the book.
        """
        if positions.empty:
            return positions.astype(float)
        turnover = positions.diff()
        turnover.iloc[0] = positions.iloc[0]
        return turnover.abs() * self.config.cost_rate

    def funding_cost(self, positions: pd.Series) -> pd.Series:
        """Perpetual-funding drag while a position is held.

        ``funding_bps_per_day`` is pro-rated to one bar. Zero by default, so it
        only bites once the user supplies a real funding assumption.
        """
        per_bar = (
            self.config.funding_bps_per_day / 1e4 * 365.0 / self.bars_per_year
        )
        return positions.abs().shift(1).fillna(0.0) * per_bar
