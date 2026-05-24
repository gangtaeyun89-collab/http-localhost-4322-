"""Strategy interface and order/intent types.

Strategies emit :class:`Intent` objects rather than placing orders directly. The
runner passes each intent through the risk gate and on to the broker, so the
same strategy class can run unchanged in paper or live mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from quant_tool.polymarket.data.models import Market, Orderbook


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Intent:
    """A strategy's desired order, pre-risk-check.

    ``size`` is in shares of the conditional token (== USDC notional at fill,
    since prices are in [0, 1]). ``post_only`` quotes never cross the spread;
    market-takers set it to ``False``.
    """

    strategy: str
    token_id: str
    side: Side
    price: float
    size: float
    post_only: bool = True

    def __post_init__(self) -> None:
        if not 0 < self.price < 1:
            raise ValueError(f"price {self.price} outside (0, 1)")
        if self.size <= 0:
            raise ValueError("size must be positive")

    @property
    def notional(self) -> float:
        return self.price * self.size


@dataclass(frozen=True)
class MarketSnapshot:
    """One refresh cycle's view of a market handed to a strategy."""

    market: Market
    yes_book: Orderbook
    no_book: Orderbook


class Strategy(Protocol):
    """Strategies must be cheap to call: ``on_snapshot`` runs every poll cycle."""

    name: str

    def on_snapshot(self, snapshot: MarketSnapshot) -> tuple[Intent, ...]:
        """Return the intents this strategy wants to submit for ``snapshot``.

        Returning an empty tuple is the no-op default. Strategies must not have
        side effects beyond updating their own state; the runner owns I/O.
        """
        ...
