"""Portfolio allocation: construct, backtest and rebalance an asset mix.

Distinct from the pairs-trading layers -- this is *beta* not *alpha*: it does
not try to beat the market, it captures it with a deliberate, diversified,
systematically rebalanced asset mix. The right tool for a long-horizon
portfolio.
"""

from quant_tool.allocation.backtest import AllocationResult, backtest_allocation
from quant_tool.allocation.construction import (
    inverse_volatility_weights,
    minimum_variance_weights,
    rebalancing_trades,
    strategic_weights,
)
from quant_tool.allocation.report import (
    PortfolioReport,
    Sleeve,
    SleeveReport,
    build_report,
)

__all__ = [
    "AllocationResult",
    "backtest_allocation",
    "strategic_weights",
    "inverse_volatility_weights",
    "minimum_variance_weights",
    "rebalancing_trades",
    "PortfolioReport",
    "Sleeve",
    "SleeveReport",
    "build_report",
]
