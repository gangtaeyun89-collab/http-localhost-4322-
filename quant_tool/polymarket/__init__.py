"""Polymarket auto-trading subsystem.

The Polymarket subsystem is independent of the crypto stat-arb tooling in the
rest of ``quant_tool``: it has its own market-data clients, execution layer,
strategies, and risk module. The two share only the dataclass/validation style.

Top-level entry points live in :mod:`quant_tool.polymarket.runner`.
"""

from quant_tool.polymarket.config import PolymarketConfig, RiskLimits
from quant_tool.polymarket.env import PolymarketEnv, from_environ, load_dotenv

__all__ = ["PolymarketConfig", "RiskLimits", "PolymarketEnv", "from_environ", "load_dotenv"]
