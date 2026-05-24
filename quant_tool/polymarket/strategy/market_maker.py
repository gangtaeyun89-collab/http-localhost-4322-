"""Simple inventory-skewed market maker.

Quotes both sides one tick inside the best bid/ask, shifting the mid by
``inventory_skew`` per unit of net position to discourage one-sided fills. This
is the simplest profitable MM heuristic; once the bake-off shows it has edge we
can upgrade to Avellaneda-Stoikov with explicit risk aversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quant_tool.polymarket.strategy.base import Intent, MarketSnapshot, Side


@dataclass
class MarketMaker:
    name: str = "market_maker"
    quote_size: float = 20.0  # shares per side
    min_spread_ticks: int = 2
    inventory_skew: float = 0.001  # price shift per share of net inventory
    max_inventory_shares: float = 200.0

    inventory: dict[str, float] = field(default_factory=dict)  # token_id -> signed shares

    def on_fill(self, token_id: str, side: Side, size: float) -> None:
        signed = size if side is Side.BUY else -size
        self.inventory[token_id] = self.inventory.get(token_id, 0.0) + signed

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
            tick = snapshot.market.tick_size
            if (best_ask.price - best_bid.price) < self.min_spread_ticks * tick:
                continue  # spread already tight; we'd be the worst quote

            mid = 0.5 * (best_bid.price + best_ask.price)
            inv = self.inventory.get(token.token_id, 0.0)
            if abs(inv) >= self.max_inventory_shares:
                # Only allow the reducing side when we're capped.
                reducing_side = Side.SELL if inv > 0 else Side.BUY
                quote = self._quote(mid, tick, inv, reducing_side)
                if quote is not None:
                    intents.append(Intent(self.name, token.token_id, reducing_side, quote, self.quote_size))
                continue

            bid = self._quote(mid, tick, inv, Side.BUY)
            ask = self._quote(mid, tick, inv, Side.SELL)
            if bid is not None:
                intents.append(Intent(self.name, token.token_id, Side.BUY, bid, self.quote_size))
            if ask is not None:
                intents.append(Intent(self.name, token.token_id, Side.SELL, ask, self.quote_size))
        return tuple(intents)

    def _quote(self, mid: float, tick: float, inventory: float, side: Side) -> float | None:
        skew = self.inventory_skew * inventory
        half_spread = tick  # one tick inside mid
        raw = mid - skew + (-half_spread if side is Side.BUY else half_spread)
        # Round to tick grid and clamp inside (0, 1).
        snapped = round(raw / tick) * tick
        if not 0 < snapped < 1:
            return None
        return snapped
