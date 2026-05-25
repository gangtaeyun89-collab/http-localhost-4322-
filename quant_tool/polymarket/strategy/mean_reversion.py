"""Mean-reversion taker.

Polymarket markets often over-react to news prints. When the mid moves more
than ``move_threshold`` over ``lookback_cycles`` cycles, this strategy takes
the *opposite* side at the new best bid/ask, betting on a partial reversion.

Pure taker (post_only=False) -- no resting orders, no adverse selection from
stale quotes. Low frequency by design: most cycles do nothing, so the strategy
should be cheap (no inventory accumulation) and the few fills should land at
attractive prices.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from quant_tool.polymarket.strategy.base import Intent, MarketSnapshot, Side


@dataclass
class MeanReversion:
    name: str = "mean_reversion"
    lookback_cycles: int = 3
    move_threshold: float = 0.03   # price units (3 cents on tick=0.01)
    take_size: float = 10.0
    min_price: float = 0.10        # ignore near-certain markets
    max_price: float = 0.90

    # token_id -> recent mid prices in cycle order
    _history: dict[str, deque] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=20)),
    )

    def on_snapshot(self, snapshot: MarketSnapshot) -> tuple[Intent, ...]:
        intents: list[Intent] = []
        for book, token in (
            (snapshot.yes_book, snapshot.market.yes_token()),
            (snapshot.no_book, snapshot.market.no_token()),
        ):
            mid = book.mid()
            if mid is None or mid < self.min_price or mid > self.max_price:
                continue
            hist = self._history[token.token_id]
            hist.append(mid)
            if len(hist) < self.lookback_cycles + 1:
                continue

            old_mid = hist[-(self.lookback_cycles + 1)]
            move = mid - old_mid
            if abs(move) < self.move_threshold:
                continue

            # Big positive move -> over-reaction up -> SELL into it.
            # Big negative move -> over-reaction down -> BUY into it.
            if move > 0:
                bb = book.best_bid()
                if bb is None:
                    continue
                intents.append(Intent(self.name, token.token_id, Side.SELL,
                                       bb.price, self.take_size, post_only=False))
            else:
                ba = book.best_ask()
                if ba is None:
                    continue
                intents.append(Intent(self.name, token.token_id, Side.BUY,
                                       ba.price, self.take_size, post_only=False))
        return tuple(intents)
