"""Polymarket strategies.

All strategies implement :class:`quant_tool.polymarket.strategy.base.Strategy` and
are looked up by name in :data:`STRATEGY_REGISTRY`. The runner instantiates each
named strategy once per session and dispatches market snapshots to it.
"""

from quant_tool.polymarket.strategy.base import Intent, Side, Strategy
from quant_tool.polymarket.strategy.market_maker import MarketMaker
from quant_tool.polymarket.strategy.smart_market_maker import SmartMarketMaker
from quant_tool.polymarket.strategy.arb_yes_no import YesNoArb
from quant_tool.polymarket.strategy.copy_trader import CopyTrader
from quant_tool.polymarket.strategy.signal_model import SignalModel
from quant_tool.polymarket.strategy.mean_reversion import MeanReversion

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "market_maker": MarketMaker,
    "smart_market_maker": SmartMarketMaker,
    "arb_yes_no": YesNoArb,
    "copy_trader": CopyTrader,
    "signal_model": SignalModel,
    "mean_reversion": MeanReversion,
}

__all__ = [
    "Intent",
    "Side",
    "Strategy",
    "STRATEGY_REGISTRY",
    "MarketMaker",
    "SmartMarketMaker",
    "YesNoArb",
    "CopyTrader",
    "SignalModel",
    "MeanReversion",
]
