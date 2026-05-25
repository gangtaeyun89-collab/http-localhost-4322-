"""Plain-data types shared by the Polymarket data, strategy, and execution layers.

Polymarket binary markets resolve to YES or NO. Each outcome trades as an ERC-1155
conditional token with a distinct ``token_id``. Prices are probabilities in [0, 1]
denominated in USDC; YES + NO prices sum to ~1 at equilibrium, and any deviation
is the basis for the YES/NO arbitrage strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Token:
    """One side (YES or NO) of a Polymarket binary market."""

    token_id: str
    outcome: str  # "Yes" or "No" as reported by the API

    def __post_init__(self) -> None:
        if not self.token_id:
            raise ValueError("token_id must be non-empty")
        if not self.outcome:
            raise ValueError("outcome must be non-empty")


@dataclass(frozen=True)
class Market:
    """A tradable Polymarket binary market.

    ``condition_id`` is the on-chain identifier; ``tokens`` carries the two
    outcome tokens. ``tick_size`` is the minimum price increment (e.g. 0.01).
    """

    condition_id: str
    question: str
    tokens: tuple[Token, Token]
    tick_size: float
    min_order_size: float
    end_date: datetime | None
    closed: bool
    active: bool

    def __post_init__(self) -> None:
        if len(self.tokens) != 2:
            raise ValueError("Polymarket binary markets must have exactly two tokens")
        if not 0 < self.tick_size < 1:
            raise ValueError("tick_size must be in (0, 1)")
        if self.min_order_size <= 0:
            raise ValueError("min_order_size must be positive")

    def yes_token(self) -> Token:
        for token in self.tokens:
            if token.outcome.lower() == "yes":
                return token
        raise ValueError(f"no YES token on market {self.condition_id}")

    def no_token(self) -> Token:
        for token in self.tokens:
            if token.outcome.lower() == "no":
                return token
        raise ValueError(f"no NO token on market {self.condition_id}")


@dataclass(frozen=True)
class OrderbookLevel:
    price: float
    size: float

    def __post_init__(self) -> None:
        if not 0 <= self.price <= 1:
            raise ValueError(f"price {self.price} outside [0, 1]")
        if self.size < 0:
            raise ValueError("size must be non-negative")


@dataclass(frozen=True)
class Orderbook:
    """One-sided order book snapshot for a single conditional token.

    ``bids`` are sorted high-to-low, ``asks`` low-to-high. Empty tuples mean no
    resting orders on that side (common on illiquid markets).
    """

    token_id: str
    bids: tuple[OrderbookLevel, ...]
    asks: tuple[OrderbookLevel, ...]
    timestamp: datetime

    def best_bid(self) -> OrderbookLevel | None:
        return self.bids[0] if self.bids else None

    def best_ask(self) -> OrderbookLevel | None:
        return self.asks[0] if self.asks else None

    def mid(self) -> float | None:
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return 0.5 * (bb.price + ba.price)

    def spread(self) -> float | None:
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return ba.price - bb.price


@dataclass(frozen=True)
class Trade:
    """A printed trade on a conditional token."""

    token_id: str
    price: float
    size: float
    side: str  # "BUY" or "SELL" (taker side)
    timestamp: datetime
