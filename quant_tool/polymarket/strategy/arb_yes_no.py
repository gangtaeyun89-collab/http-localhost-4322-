"""YES/NO complementary-pair arbitrage.

For a binary market, YES and NO must sum to 1 at expiry. If best-bid(YES) +
best-bid(NO) > 1 + costs, selling both legs locks in the difference. If
best-ask(YES) + best-ask(NO) < 1 - costs, buying both legs does the same. This
arb appears mostly on illiquid markets and during news shocks.
"""

from __future__ import annotations

from dataclasses import dataclass

from quant_tool.polymarket.strategy.base import Intent, MarketSnapshot, Side


@dataclass
class YesNoArb:
    name: str = "arb_yes_no"
    min_edge: float = 0.005  # 0.5 cents per share after fees
    max_clip_shares: float = 100.0

    def on_snapshot(self, snapshot: MarketSnapshot) -> tuple[Intent, ...]:
        yes_bid = snapshot.yes_book.best_bid()
        yes_ask = snapshot.yes_book.best_ask()
        no_bid = snapshot.no_book.best_bid()
        no_ask = snapshot.no_book.best_ask()

        intents: list[Intent] = []
        # Sell both: pay out 1, receive yes_bid + no_bid.
        if yes_bid is not None and no_bid is not None:
            edge = (yes_bid.price + no_bid.price) - 1.0
            if edge > self.min_edge:
                size = min(yes_bid.size, no_bid.size, self.max_clip_shares)
                if size > 0:
                    intents.append(Intent(self.name, snapshot.market.yes_token().token_id,
                                          Side.SELL, yes_bid.price, size, post_only=False))
                    intents.append(Intent(self.name, snapshot.market.no_token().token_id,
                                          Side.SELL, no_bid.price, size, post_only=False))
                    return tuple(intents)

        # Buy both: receive 1 at expiry, pay yes_ask + no_ask.
        if yes_ask is not None and no_ask is not None:
            edge = 1.0 - (yes_ask.price + no_ask.price)
            if edge > self.min_edge:
                size = min(yes_ask.size, no_ask.size, self.max_clip_shares)
                if size > 0:
                    intents.append(Intent(self.name, snapshot.market.yes_token().token_id,
                                          Side.BUY, yes_ask.price, size, post_only=False))
                    intents.append(Intent(self.name, snapshot.market.no_token().token_id,
                                          Side.BUY, no_ask.price, size, post_only=False))

        return tuple(intents)
