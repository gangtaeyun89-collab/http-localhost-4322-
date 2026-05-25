"""Signal-driven directional strategy.

Bake-off baseline: short-window momentum on the trade-printed mid. When the mid
crosses above its EMA and the order book is thicker on the ask side (taker
buying pressure), we lift the offer; symmetric short on the YES token is left
as a future enhancement once we add an external-news signal source.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from quant_tool.polymarket.strategy.base import Intent, MarketSnapshot, Side


@dataclass
class _EmaState:
    value: float | None = None

    def update(self, x: float, alpha: float) -> float:
        self.value = x if self.value is None else (1 - alpha) * self.value + alpha * x
        return self.value


@dataclass
class SignalModel:
    name: str = "signal_model"
    ema_alpha: float = 0.2  # ~5-period EMA
    momentum_threshold: float = 0.01
    take_size_shares: float = 15.0
    book_imbalance_min: float = 1.5  # ask-size / bid-size ratio required for a long

    _ema: dict[str, _EmaState] = field(default_factory=lambda: defaultdict(_EmaState))

    def on_snapshot(self, snapshot: MarketSnapshot) -> tuple[Intent, ...]:
        intents: list[Intent] = []
        for book, token in (
            (snapshot.yes_book, snapshot.market.yes_token()),
            (snapshot.no_book, snapshot.market.no_token()),
        ):
            best_bid = book.best_bid()
            best_ask = book.best_ask()
            if best_bid is None or best_ask is None:
                continue
            mid = 0.5 * (best_bid.price + best_ask.price)
            ema = self._ema[token.token_id].update(mid, self.ema_alpha)
            if mid - ema <= self.momentum_threshold:
                continue
            ask_depth = sum(level.size for level in book.asks[:3])
            bid_depth = sum(level.size for level in book.bids[:3]) or 1e-9
            if ask_depth / bid_depth < self.book_imbalance_min:
                continue
            intents.append(Intent(self.name, token.token_id, Side.BUY,
                                  best_ask.price, self.take_size_shares, post_only=False))
        return tuple(intents)
