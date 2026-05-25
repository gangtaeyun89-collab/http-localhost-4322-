"""Order routing layer.

Two implementations of :class:`Broker` exist: :class:`PaperBroker` for the bake
off and (planned) ``ClobBroker`` for live trading once the user has Polymarket
API credentials. The runner depends on the protocol, not the concrete class.
"""

from quant_tool.polymarket.execution.paper_broker import PaperBroker, Fill, Position

__all__ = ["PaperBroker", "Fill", "Position"]
