"""Polymarket strategies.

All strategies implement :class:`quant_tool.polymarket.strategy.base.Strategy` and
are looked up by name in :data:`STRATEGY_REGISTRY`. The runner instantiates each
named strategy once per session and dispatches market snapshots to it.
"""

from quant_tool.polymarket.strategy.base import Intent, Side, Strategy
from quant_tool.polymarket.strategy.market_maker import MarketMaker
from quant_tool.polymarket.strategy.arb_yes_no import YesNoArb
from quant_tool.polymarket.strategy.copy_trader import CopyTrader
from quant_tool.polymarket.strategy.signal_model import SignalModel

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "market_maker": MarketMaker,
    "arb_yes_no": YesNoArb,
    "copy_trader": CopyTrader,
    "signal_model": SignalModel,
}

__all__ = [
    "Intent",
    "Side",
    "Strategy",
    "STRATEGY_REGISTRY",
    "MarketMaker",
    "YesNoArb",
    "CopyTrader",
    "SignalModel",
]
