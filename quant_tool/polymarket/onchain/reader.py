"""Read-only on-chain queries for the Polymarket proxy wallet.

Two data sources:

* **Polygon RPC** for the spot USDC.e balance. Standard ERC-20 ``balanceOf``
  call -- works against any Polygon JSON-RPC endpoint (public, Alchemy, Infura).
* **Polymarket's data-api** for open conditional-token positions. This is the
  same endpoint the polymarket.com UI uses; it returns enriched data
  (market question, current price, PnL) so we don't need to walk the on-chain
  ERC-1155 token IDs ourselves.

Both sources are HTTP, so we reuse the same opener pattern as the CLOB/Gamma
clients. Tests inject a fake opener and never touch the network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.request import Request, urlopen


USDC_E_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
"""USDC.e on Polygon -- 6-decimal ERC-20 used by Polymarket for collateral."""

USDC_E_DECIMALS = 6

# ERC-20 balanceOf(address) function selector + 32-byte padded address.
_BALANCE_OF_SELECTOR = "0x70a08231"


Opener = Callable[[Request, float], "object"]


def _default_opener(request: Request, timeout: float):
    return urlopen(request, timeout=timeout)


@dataclass(frozen=True)
class Position:
    """One open Polymarket position on a conditional token."""

    condition_id: str
    token_id: str
    outcome: str  # "Yes" / "No"
    market_question: str
    size: float            # shares
    avg_price: float       # entry price
    current_price: float   # latest mid
    current_value: float   # size * current_price (mark-to-market)
    realised_pnl: float
    unrealised_pnl: float


@dataclass(frozen=True)
class WalletSnapshot:
    """Point-in-time view of a Polymarket wallet's cash + positions."""

    address: str
    usdc_balance: float
    positions: tuple[Position, ...]
    total_position_value: float
    total_equity: float    # usdc + sum(position values)
    realised_pnl_total: float
    unrealised_pnl_total: float
    fetched_at: datetime


@dataclass(frozen=True)
class WalletReader:
    """Synchronous reader for wallet state. Inject ``opener`` for tests."""

    polygon_rpc_url: str = "https://polygon-rpc.com"
    data_api_url: str = "https://data-api.polymarket.com"
    timeout: float = 10.0
    opener: Opener = _default_opener

    # ----- public API ----------------------------------------------------

    def usdc_balance(self, address: str) -> float:
        """Return USDC.e balance of ``address`` in human-readable USDC."""
        data = _BALANCE_OF_SELECTOR + _pad_address(address)
        raw = self._rpc("eth_call", [{"to": USDC_E_CONTRACT, "data": data}, "latest"])
        if not isinstance(raw, str) or not raw.startswith("0x"):
            return 0.0
        wei = int(raw, 16)
        return wei / (10 ** USDC_E_DECIMALS)

    def positions(self, address: str) -> tuple[Position, ...]:
        """Open conditional-token positions held by ``address``."""
        payload = self._http_get(self.data_api_url, "/positions", {"user": address})
        if not isinstance(payload, list):
            return ()
        return tuple(p for raw in payload if (p := _parse_position(raw)) is not None)

    def snapshot(self, address: str) -> WalletSnapshot:
        """Combined cash + positions snapshot. Errors on each call fall through to defaults."""
        try:
            usdc = self.usdc_balance(address)
        except Exception:  # noqa: BLE001
            usdc = 0.0
        try:
            positions = self.positions(address)
        except Exception:  # noqa: BLE001
            positions = ()
        total_pos = sum(p.current_value for p in positions)
        realised = sum(p.realised_pnl for p in positions)
        unrealised = sum(p.unrealised_pnl for p in positions)
        return WalletSnapshot(
            address=address,
            usdc_balance=usdc,
            positions=positions,
            total_position_value=total_pos,
            total_equity=usdc + total_pos,
            realised_pnl_total=realised,
            unrealised_pnl_total=unrealised,
            fetched_at=datetime.now(timezone.utc),
        )

    # ----- HTTP plumbing -------------------------------------------------

    def _rpc(self, method: str, params: list) -> object:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        request = Request(
            self.polygon_rpc_url, data=body,
            headers={"Content-Type": "application/json",
                     "Accept": "application/json",
                     "User-Agent": "quant_tool/polymarket"},
            method="POST",
        )
        with self.opener(request, self.timeout) as response:  # type: ignore[arg-type]
            payload = json.loads(response.read())
        if isinstance(payload, dict) and "result" in payload:
            return payload["result"]
        raise RuntimeError(f"RPC error: {payload!r}")

    def _http_get(self, base: str, path: str, params: dict) -> object:
        from urllib.parse import urlencode
        request = Request(
            f"{base}{path}?{urlencode(params)}",
            headers={"Accept": "application/json", "User-Agent": "quant_tool/polymarket"},
        )
        with self.opener(request, self.timeout) as response:  # type: ignore[arg-type]
            return json.loads(response.read())


# ---------- helpers ------------------------------------------------------


def _pad_address(address: str) -> str:
    """Encode an address as a 32-byte hex string (lowercase, no 0x prefix)."""
    addr = address.lower().removeprefix("0x")
    if len(addr) != 40:
        raise ValueError(f"address must be 20 bytes (40 hex chars), got {address!r}")
    return addr.rjust(64, "0")


def _parse_position(raw: object) -> Position | None:
    """Parse one entry from data-api ``/positions``.

    Polymarket's data-api uses camelCase keys; we tolerate either case and skip
    entries we can't make sense of. The fields we care about are stable across
    the API's revisions.
    """
    if not isinstance(raw, dict):
        return None
    try:
        size = float(raw.get("size") or 0)
        if size == 0:
            return None  # closed positions sometimes still come back with size=0
        return Position(
            condition_id=str(raw.get("conditionId") or raw.get("condition_id") or ""),
            token_id=str(raw.get("asset") or raw.get("tokenId") or raw.get("token_id") or ""),
            outcome=str(raw.get("outcome") or ""),
            market_question=str(raw.get("title") or raw.get("question") or ""),
            size=size,
            avg_price=float(raw.get("avgPrice") or raw.get("avg_price") or 0),
            current_price=float(raw.get("curPrice") or raw.get("current_price") or 0),
            current_value=float(raw.get("currentValue") or raw.get("current_value")
                                 or (size * float(raw.get("curPrice") or 0))),
            realised_pnl=float(raw.get("realizedPnl") or raw.get("realized_pnl") or 0),
            unrealised_pnl=float(raw.get("cashPnl") or raw.get("unrealized_pnl") or 0),
        )
    except (TypeError, ValueError):
        return None
