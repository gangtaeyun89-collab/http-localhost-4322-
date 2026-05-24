"""Live smoke test for the Polymarket bake-off runner.

Pulls the active-market universe from Gamma, fetches YES/NO orderbooks for the
top ``--markets`` most liquid, runs every registered strategy on each snapshot,
and prints the intents each strategy would have submitted. No orders are placed
and no credentials are required.

Usage:
    python scripts/polymarket_smoke.py [--markets 10] [--strategies market_maker,arb_yes_no]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from quant_tool.polymarket import load_dotenv
from quant_tool.polymarket.data.clob_client import ClobClient
from quant_tool.polymarket.data.gamma_client import GammaClient
from quant_tool.polymarket.data.models import Market, Orderbook
from quant_tool.polymarket.strategy import STRATEGY_REGISTRY
from quant_tool.polymarket.strategy.base import MarketSnapshot


@dataclass
class MarketResult:
    market: Market
    yes_bid: float | None
    yes_ask: float | None
    no_bid: float | None
    no_ask: float | None
    intents_by_strategy: dict[str, int]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--markets", type=int, default=10,
                   help="Number of markets to fetch books for (default: 10)")
    p.add_argument("--strategies", type=str, default=",".join(STRATEGY_REGISTRY),
                   help="Comma-separated strategy names (default: all registered)")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Log each fetched book")
    p.add_argument("--save", type=Path, default=None,
                   help="If set, write the fetched snapshots to this JSON path "
                        "so they can be replayed offline.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    load_dotenv()
    gamma = GammaClient()
    clob = ClobClient()

    names = [n.strip() for n in args.strategies.split(",") if n.strip()]
    unknown = [n for n in names if n not in STRATEGY_REGISTRY]
    if unknown:
        print(f"error: unknown strategies: {unknown}", file=sys.stderr)
        return 2
    strategies = [STRATEGY_REGISTRY[n]() for n in names]

    print(f"Fetching active-market universe from {gamma.base_url}...")
    universe = gamma.active_markets(limit=200)
    print(f"  -> {len(universe)} markets")
    if not universe:
        print("no markets returned; aborting.")
        return 1

    sample = universe[: args.markets]
    print(f"Sampling first {len(sample)} markets and running {len(strategies)} strategies on each.\n")

    results: list[MarketResult] = []
    captured: list[dict] = []
    for market in sample:
        try:
            yes_book = clob.orderbook(market.yes_token().token_id)
            no_book = clob.orderbook(market.no_token().token_id)
        except Exception as exc:  # noqa: BLE001
            print(f"  [skip] {market.question[:60]!r}: {exc}")
            continue

        snap = MarketSnapshot(market=market, yes_book=yes_book, no_book=no_book)
        counts: dict[str, int] = {}
        for strategy in strategies:
            intents = strategy.on_snapshot(snap)
            counts[strategy.name] = len(intents)

        yb, ya = yes_book.best_bid(), yes_book.best_ask()
        nb, na = no_book.best_bid(), no_book.best_ask()
        results.append(MarketResult(
            market=market,
            yes_bid=yb.price if yb else None,
            yes_ask=ya.price if ya else None,
            no_bid=nb.price if nb else None,
            no_ask=na.price if na else None,
            intents_by_strategy=counts,
        ))
        if args.save is not None:
            captured.append(_serialize_snapshot(snap, counts))

    _print_table(results, names)
    _print_summary(results, names)

    if args.save is not None:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps({
            "captured_at": datetime.utcnow().isoformat() + "Z",
            "universe_size": len(universe),
            "snapshots": captured,
        }, indent=2))
        print(f"\nSaved {len(captured)} snapshots to {args.save}")
    return 0


def _serialize_snapshot(snap: MarketSnapshot, counts: dict[str, int]) -> dict:
    return {
        "market": {
            "condition_id": snap.market.condition_id,
            "question": snap.market.question,
            "tick_size": snap.market.tick_size,
            "min_order_size": snap.market.min_order_size,
            "tokens": [{"token_id": t.token_id, "outcome": t.outcome} for t in snap.market.tokens],
        },
        "yes_book": _serialize_book(snap.yes_book),
        "no_book": _serialize_book(snap.no_book),
        "intents_by_strategy": counts,
    }


def _serialize_book(book: Orderbook) -> dict:
    return {
        "token_id": book.token_id,
        "timestamp": book.timestamp.isoformat(),
        "bids": [{"price": lvl.price, "size": lvl.size} for lvl in book.bids],
        "asks": [{"price": lvl.price, "size": lvl.size} for lvl in book.asks],
    }


def _print_table(results: list[MarketResult], strategies: list[str]) -> None:
    header = ["Question", "YES bid/ask", "NO bid/ask"] + strategies
    widths = [38, 13, 13] + [max(len(s), 4) for s in strategies]
    print(" | ".join(h.ljust(w) for h, w in zip(header, widths)))
    print("-+-".join("-" * w for w in widths))
    for r in results:
        row = [
            (r.market.question[:35] + "...") if len(r.market.question) > 38 else r.market.question,
            _fmt_pair(r.yes_bid, r.yes_ask),
            _fmt_pair(r.no_bid, r.no_ask),
        ] + [str(r.intents_by_strategy.get(s, 0)) for s in strategies]
        print(" | ".join(c.ljust(w) for c, w in zip(row, widths)))


def _fmt_pair(bid: float | None, ask: float | None) -> str:
    b = f"{bid:.3f}" if bid is not None else "  -  "
    a = f"{ask:.3f}" if ask is not None else "  -  "
    return f"{b}/{a}"


def _print_summary(results: list[MarketResult], strategies: list[str]) -> None:
    print()
    print("Strategy summary (markets with intents / total markets):")
    for s in strategies:
        active = sum(1 for r in results if r.intents_by_strategy.get(s, 0) > 0)
        total_intents = sum(r.intents_by_strategy.get(s, 0) for r in results)
        print(f"  {s:<15} {active}/{len(results)} markets, {total_intents} intents total")


if __name__ == "__main__":
    raise SystemExit(main())
