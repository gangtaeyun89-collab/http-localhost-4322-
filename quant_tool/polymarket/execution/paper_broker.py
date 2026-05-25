"""Paper-trading broker.

Fills are simulated against the live order book observed at intent time:

    * A taker intent (``post_only=False``) crosses the spread and fills
      immediately at the resting opposite-side price, capped by the resting size.
    * A maker intent (``post_only=True``) rests until a later snapshot prints a
      trade that crosses it. The broker tracks resting orders in
      :attr:`open_orders` and matches them in :meth:`on_book`.

PnL is marked to mid on every equity poll. Realised PnL accrues on every
opposite-side fill that reduces a position; the cost basis is a per-token
running average.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import count

from quant_tool.polymarket.data.models import Orderbook
from quant_tool.polymarket.strategy.base import Intent, Side


_ORDER_IDS = count(1)


@dataclass
class Fill:
    order_id: int
    strategy: str
    token_id: str
    side: Side
    price: float
    size: float
    timestamp: datetime


@dataclass
class Position:
    """Running average-cost position in one conditional token."""
    shares: float = 0.0  # signed: positive = long
    avg_price: float = 0.0
    realised_pnl: float = 0.0

    def apply(self, side: Side, price: float, size: float) -> None:
        signed = size if side is Side.BUY else -size
        new_shares = self.shares + signed
        if self.shares == 0 or (self.shares > 0) == (signed > 0):
            # Opening or adding -- update average cost on the absolute side.
            total_cost = abs(self.shares) * self.avg_price + size * price
            self.avg_price = total_cost / abs(new_shares) if new_shares != 0 else 0.0
        else:
            # Reducing or flipping -- realise PnL on the reduced quantity.
            reduce_qty = min(abs(signed), abs(self.shares))
            sign = 1 if self.shares > 0 else -1
            self.realised_pnl += reduce_qty * (price - self.avg_price) * sign
            if abs(signed) > abs(self.shares):
                # Flipped past flat: remainder opens a new position at fill price.
                self.avg_price = price
            elif new_shares == 0:
                self.avg_price = 0.0
        self.shares = new_shares


@dataclass
class _RestingOrder:
    order_id: int
    intent: Intent


@dataclass
class PaperBroker:
    """In-memory simulation of order placement against a live order book."""
    starting_cash: float = 10_000.0
    cash: float = 0.0
    positions: dict[str, Position] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    open_orders: dict[int, _RestingOrder] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cash = self.starting_cash

    # ----- order entry --------------------------------------------------

    def submit(self, intent: Intent, book: Orderbook, now: datetime | None = None) -> Fill | None:
        """Submit an intent. Returns a Fill if it crosses immediately, else None.

        ``book`` must be for ``intent.token_id``; the broker does not look it up.
        """
        if book.token_id != intent.token_id:
            raise ValueError("book token_id does not match intent")
        ts = now or datetime.now(timezone.utc)

        if not intent.post_only:
            return self._cross(intent, book, ts)

        # Post-only: would it cross? If yes, reject (matches CLOB behaviour).
        opposite = book.best_ask() if intent.side is Side.BUY else book.best_bid()
        if opposite is not None:
            would_cross = (intent.side is Side.BUY and intent.price >= opposite.price) or \
                          (intent.side is Side.SELL and intent.price <= opposite.price)
            if would_cross:
                return None
        order_id = next(_ORDER_IDS)
        self.open_orders[order_id] = _RestingOrder(order_id=order_id, intent=intent)
        return None

    def _cross(self, intent: Intent, book: Orderbook, ts: datetime) -> Fill | None:
        opposite = book.best_ask() if intent.side is Side.BUY else book.best_bid()
        if opposite is None:
            return None
        if intent.side is Side.BUY and intent.price < opposite.price:
            return None
        if intent.side is Side.SELL and intent.price > opposite.price:
            return None
        size = min(intent.size, opposite.size)
        if size <= 0:
            return None
        return self._record_fill(intent.strategy, intent.token_id, intent.side, opposite.price, size, ts)

    # ----- maker-order matching on subsequent book updates --------------

    def on_book(self, book: Orderbook, now: datetime | None = None) -> list[Fill]:
        """Match resting maker orders against a fresh book snapshot.

        A resting bid at price p fills when an ask appears at <= p, etc. This is
        an optimistic fill model -- in reality a maker only fills when a taker
        crosses *into* the order. For the bake-off the optimistic model lets us
        upper-bound MM PnL; we'll tighten it once we add trade prints.
        """
        ts = now or datetime.now(timezone.utc)
        fills: list[Fill] = []
        to_remove: list[int] = []
        for order_id, resting in self.open_orders.items():
            if resting.intent.token_id != book.token_id:
                continue
            opposite = book.best_ask() if resting.intent.side is Side.BUY else book.best_bid()
            if opposite is None:
                continue
            crosses = (resting.intent.side is Side.BUY and opposite.price <= resting.intent.price) or \
                      (resting.intent.side is Side.SELL and opposite.price >= resting.intent.price)
            if not crosses:
                continue
            size = min(resting.intent.size, opposite.size)
            if size <= 0:
                continue
            fills.append(self._record_fill(
                resting.intent.strategy, resting.intent.token_id, resting.intent.side,
                resting.intent.price, size, ts,
            ))
            to_remove.append(order_id)
        for order_id in to_remove:
            self.open_orders.pop(order_id, None)
        return fills

    def cancel_all(self) -> int:
        n = len(self.open_orders)
        self.open_orders.clear()
        return n

    def cancel_all_for_strategy(self, strategy: str) -> int:
        """Cancel every resting order placed by ``strategy``. Used by smart MMs
        that want to refresh their quotes every cycle to avoid adverse selection
        from stale orders.
        """
        to_remove = [oid for oid, ro in self.open_orders.items()
                     if ro.intent.strategy == strategy]
        for oid in to_remove:
            self.open_orders.pop(oid, None)
        return len(to_remove)

    # ----- accounting ----------------------------------------------------

    def _record_fill(self, strategy: str, token_id: str, side: Side,
                     price: float, size: float, ts: datetime) -> Fill:
        position = self.positions.setdefault(token_id, Position())
        position.apply(side, price, size)
        # USDC cash impact: pay price*size on BUY, receive on SELL.
        self.cash += -price * size if side is Side.BUY else price * size
        fill = Fill(
            order_id=next(_ORDER_IDS),
            strategy=strategy, token_id=token_id, side=side,
            price=price, size=size, timestamp=ts,
        )
        self.fills.append(fill)
        return fill

    def equity(self, marks: dict[str, float]) -> float:
        """Equity = cash + mark-to-market of all positions.

        ``marks`` maps ``token_id`` to its current mid; missing entries are
        marked at the position's average price (i.e. zero unrealised PnL).
        """
        mtm = 0.0
        for token_id, pos in self.positions.items():
            mark = marks.get(token_id, pos.avg_price)
            mtm += pos.shares * mark
        return self.cash + mtm

    def realised_pnl(self) -> float:
        return sum(pos.realised_pnl for pos in self.positions.values())
