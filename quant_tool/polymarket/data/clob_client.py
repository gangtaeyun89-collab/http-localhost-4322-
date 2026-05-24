"""Read-only client for the Polymarket CLOB REST API.

Only public endpoints are wrapped here. Order placement requires a signed message
and lives in :mod:`quant_tool.polymarket.execution.clob_broker` (live mode only).

The client uses the standard library so the package imports cleanly without
``httpx`` or ``requests`` installed. Tests inject a fake ``opener`` to avoid the
network entirely.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from quant_tool.polymarket.data.models import Orderbook, OrderbookLevel, Trade


Opener = Callable[[Request, float], "object"]
"""``(request, timeout) -> response`` callable. Injectable for tests."""


def _default_opener(request: Request, timeout: float):
    # urlopen's second positional arg is ``data``, so the timeout has to be
    # passed by keyword. Wrapping it here keeps :class:`Opener` clean.
    return urlopen(request, timeout=timeout)


@dataclass(frozen=True)
class ClobClient:
    """Synchronous read-only client for the Polymarket CLOB."""

    base_url: str = "https://clob.polymarket.com"
    timeout: float = 10.0
    opener: Opener = _default_opener

    def _get(self, path: str, params: dict[str, object] | None = None) -> object:
        query = f"?{urlencode(params)}" if params else ""
        request = Request(
            f"{self.base_url}{path}{query}",
            headers={"Accept": "application/json", "User-Agent": "quant_tool/polymarket"},
        )
        with self.opener(request, self.timeout) as response:  # type: ignore[arg-type]
            return json.loads(response.read())

    def orderbook(self, token_id: str) -> Orderbook:
        """Snapshot of the order book for one conditional token."""
        payload = self._get("/book", {"token_id": token_id})
        return _parse_orderbook(token_id, payload)

    def orderbooks(self, token_ids: Iterable[str]) -> dict[str, Orderbook]:
        # CLOB exposes /books for batch retrieval but the single-token endpoint
        # is more consistent across deployments; iterate to keep behaviour simple.
        return {tid: self.orderbook(tid) for tid in token_ids}

    def midpoint(self, token_id: str) -> float | None:
        payload = self._get("/midpoint", {"token_id": token_id})
        mid = payload.get("mid") if isinstance(payload, dict) else None
        return float(mid) if mid is not None else None

    def last_trade_price(self, token_id: str) -> float | None:
        payload = self._get("/last-trade-price", {"token_id": token_id})
        price = payload.get("price") if isinstance(payload, dict) else None
        return float(price) if price is not None else None

    def trades(self, token_id: str, limit: int = 100) -> tuple[Trade, ...]:
        payload = self._get("/trades", {"market": token_id, "limit": limit})
        if not isinstance(payload, list):
            return ()
        return tuple(_parse_trade(token_id, item) for item in payload if isinstance(item, dict))


def _parse_orderbook(token_id: str, payload: object) -> Orderbook:
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected orderbook payload: {type(payload).__name__}")
    bids = tuple(sorted(
        (_parse_level(b) for b in payload.get("bids", []) if isinstance(b, dict)),
        key=lambda lvl: lvl.price,
        reverse=True,
    ))
    asks = tuple(sorted(
        (_parse_level(a) for a in payload.get("asks", []) if isinstance(a, dict)),
        key=lambda lvl: lvl.price,
    ))
    timestamp = _parse_timestamp(payload.get("timestamp"))
    return Orderbook(token_id=token_id, bids=bids, asks=asks, timestamp=timestamp)


def _parse_level(raw: dict) -> OrderbookLevel:
    return OrderbookLevel(price=float(raw["price"]), size=float(raw["size"]))


def _parse_trade(token_id: str, raw: dict) -> Trade:
    return Trade(
        token_id=token_id,
        price=float(raw["price"]),
        size=float(raw["size"]),
        side=str(raw.get("side", "BUY")).upper(),
        timestamp=_parse_timestamp(raw.get("timestamp")),
    )


def _parse_timestamp(raw: object) -> datetime:
    if raw is None:
        return datetime.now(timezone.utc)
    # Polymarket returns milliseconds-since-epoch as a string on most endpoints.
    try:
        return datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
