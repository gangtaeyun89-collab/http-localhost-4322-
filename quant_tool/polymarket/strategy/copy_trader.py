"""Copy trader: mirror recent trades of a configured set of wallets.

The wallet list is the strategy's edge -- it should be populated with addresses
that have a track record on Polymarket (Dune/Goldsky leaderboards). For the
paper bake-off the strategy is a stub: it emits no intents unless followed
wallets have been recorded via :meth:`record_follow_trade`, which the runner
populates from the Polymarket activity feed (subgraph) once that ingestion is
wired up.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from quant_tool.polymarket.strategy.base import Intent, MarketSnapshot, Side


@dataclass
class FollowTrade:
    wallet: str
    token_id: str
    side: Side
    price: float
    size: float
    timestamp: datetime


@dataclass
class CopyTrader:
    name: str = "copy_trader"
    followed_wallets: frozenset[str] = field(default_factory=frozenset)
    mirror_window: timedelta = field(default_factory=lambda: timedelta(minutes=15))
    mirror_size_shares: float = 25.0
    max_price_slippage: float = 0.01

    _recent: deque[FollowTrade] = field(default_factory=lambda: deque(maxlen=2000))

    def record_follow_trade(self, trade: FollowTrade) -> None:
        if trade.wallet in self.followed_wallets:
            self._recent.append(trade)

    def on_snapshot(self, snapshot: MarketSnapshot) -> tuple[Intent, ...]:
        if not self._recent:
            return ()
        now = datetime.now(timezone.utc)
        cutoff = now - self.mirror_window
        intents: list[Intent] = []
        token_ids = {t.token_id for t in snapshot.market.tokens}
        for trade in list(self._recent):
            if trade.timestamp < cutoff:
                continue
            if trade.token_id not in token_ids:
                continue
            book = snapshot.yes_book if trade.token_id == snapshot.market.yes_token().token_id else snapshot.no_book
            best_ask = book.best_ask()
            best_bid = book.best_bid()
            if trade.side is Side.BUY and best_ask is not None:
                if best_ask.price <= trade.price + self.max_price_slippage:
                    intents.append(Intent(self.name, trade.token_id, Side.BUY,
                                          best_ask.price, self.mirror_size_shares, post_only=False))
            elif trade.side is Side.SELL and best_bid is not None:
                if best_bid.price >= trade.price - self.max_price_slippage:
                    intents.append(Intent(self.name, trade.token_id, Side.SELL,
                                          best_bid.price, self.mirror_size_shares, post_only=False))
        return tuple(intents)
