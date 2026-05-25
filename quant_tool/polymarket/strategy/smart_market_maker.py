"""Smart market maker -- the upgrade over :class:`MarketMaker`.

Three improvements over the naive MM, each addressing a specific failure mode
the naive version showed in paper trading:

1. **Cancel-and-replace each cycle.** The naive MM leaves quotes resting until
   they fill, which is great when nothing moves and terrible during news.
   ``cancel_before_quoting = True`` signals the runner to cancel this
   strategy's resting orders at the start of every tick so stale quotes don't
   accumulate adverse selection.

2. **Skip markets that are bad for MM.** Extreme prices (< ``min_price`` or
   > 1 - ``min_price``) and thin top-of-book sizes (< ``min_book_size``) are
   the two biggest loss generators -- you get filled exactly when the price
   moves the wrong way.

3. **Trade-tape skew.** If recent prints are mostly BUYs, an informed taker is
   sweeping the offer side; widen our ask and tighten our bid so we don't get
   picked off. Symmetric for sells.

Inventory skew (same as naive MM) is also applied so positions mean-revert.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quant_tool.polymarket.strategy.base import Intent, MarketSnapshot, Side


@dataclass
class SmartMarketMaker:
    name: str = "smart_market_maker"
    quote_size: float = 20.0
    min_spread_ticks: int = 2
    inventory_skew: float = 0.001
    max_inventory_shares: float = 200.0
    # Filters
    min_price: float = 0.05               # skip if mid < this or > 1 - this
    min_book_size: float = 50.0           # shares at top of book
    # Trade-tape skew: per share of (buy - sell) imbalance, shift quotes by N ticks
    trade_skew_per_imbalance: float = 0.05  # ticks per unit of imbalance
    max_trade_skew_ticks: int = 3           # cap the shift

    # Signals to the runner.
    cancel_before_quoting: bool = True

    inventory: dict[str, float] = field(default_factory=dict)

    def on_fill(self, token_id: str, side: Side, size: float) -> None:
        signed = size if side is Side.BUY else -size
        self.inventory[token_id] = self.inventory.get(token_id, 0.0) + signed

    def on_snapshot(self, snapshot: MarketSnapshot) -> tuple[Intent, ...]:
        intents: list[Intent] = []
        tick = snapshot.market.tick_size

        for book, token in (
            (snapshot.yes_book, snapshot.market.yes_token()),
            (snapshot.no_book, snapshot.market.no_token()),
        ):
            best_bid = book.best_bid()
            best_ask = book.best_ask()
            if best_bid is None or best_ask is None:
                continue
            mid = 0.5 * (best_bid.price + best_ask.price)

            # Filter 1: skip extreme-probability markets
            if mid < self.min_price or mid > 1 - self.min_price:
                continue
            # Filter 2: skip thin books -- the inventory we'd accumulate isn't tradable out
            if best_bid.size < self.min_book_size or best_ask.size < self.min_book_size:
                continue
            # Filter 3: skip if spread is already tight enough that we'd be the worst quote
            if (best_ask.price - best_bid.price) < self.min_spread_ticks * tick:
                continue

            inv = self.inventory.get(token.token_id, 0.0)
            inv_skew = self.inventory_skew * inv

            # Trade-tape skew (BUYs > SELLs => raise both quotes, vice-versa)
            buys = sum(t.size for t in snapshot.trades
                        if t.token_id == token.token_id and t.side == "BUY")
            sells = sum(t.size for t in snapshot.trades
                         if t.token_id == token.token_id and t.side == "SELL")
            imbalance = buys - sells
            shift_ticks = max(-self.max_trade_skew_ticks,
                              min(self.max_trade_skew_ticks,
                                  imbalance * self.trade_skew_per_imbalance))
            tape_skew = shift_ticks * tick

            if abs(inv) >= self.max_inventory_shares:
                reducing_side = Side.SELL if inv > 0 else Side.BUY
                price = self._quote(mid, tick, inv_skew, tape_skew, reducing_side)
                if price is not None:
                    intents.append(Intent(self.name, token.token_id, reducing_side,
                                           price, self.quote_size))
                continue

            bid = self._quote(mid, tick, inv_skew, tape_skew, Side.BUY)
            ask = self._quote(mid, tick, inv_skew, tape_skew, Side.SELL)
            if bid is not None:
                intents.append(Intent(self.name, token.token_id, Side.BUY,
                                       bid, self.quote_size))
            if ask is not None:
                intents.append(Intent(self.name, token.token_id, Side.SELL,
                                       ask, self.quote_size))
        return tuple(intents)

    def _quote(self, mid: float, tick: float, inv_skew: float, tape_skew: float,
               side: Side) -> float | None:
        half_spread = tick
        # Subtract inv_skew so long inventory pushes both quotes DOWN (encouraging sells).
        # Add tape_skew so buy pressure raises both quotes (avoiding selling into demand).
        raw = mid - inv_skew + tape_skew + (-half_spread if side is Side.BUY else half_spread)
        snapped = round(raw / tick) * tick
        if not 0 < snapped < 1:
            return None
        return snapped
