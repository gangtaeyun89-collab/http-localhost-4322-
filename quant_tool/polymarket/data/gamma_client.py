"""Client for the Polymarket Gamma API (market metadata)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from quant_tool.polymarket.data.models import Market, Token


Opener = Callable[[Request, float], "object"]


@dataclass(frozen=True)
class GammaClient:
    """Synchronous read-only client for Polymarket's Gamma metadata API."""

    base_url: str = "https://gamma-api.polymarket.com"
    timeout: float = 10.0
    opener: Opener = urlopen

    def _get(self, path: str, params: dict[str, object] | None = None) -> object:
        query = f"?{urlencode(params)}" if params else ""
        request = Request(
            f"{self.base_url}{path}{query}",
            headers={"Accept": "application/json", "User-Agent": "quant_tool/polymarket"},
        )
        with self.opener(request, self.timeout) as response:  # type: ignore[arg-type]
            return json.loads(response.read())

    def active_markets(self, limit: int = 500) -> tuple[Market, ...]:
        """Active, non-closed binary markets, sorted by API default (usually volume).

        Pagination beyond ``limit`` is left to the runner; for the paper bake-off
        a single page of ~500 markets is a sane universe.
        """
        payload = self._get("/markets", {"active": "true", "closed": "false", "limit": limit})
        if not isinstance(payload, list):
            return ()
        return tuple(m for raw in payload if (m := _parse_market(raw)) is not None)

    def market(self, condition_id: str) -> Market | None:
        payload = self._get("/markets", {"condition_ids": condition_id})
        if isinstance(payload, list) and payload:
            return _parse_market(payload[0])
        if isinstance(payload, dict):
            return _parse_market(payload)
        return None


def _parse_market(raw: object) -> Market | None:
    if not isinstance(raw, dict):
        return None
    condition_id = raw.get("conditionId") or raw.get("condition_id")
    question = raw.get("question")
    token_ids = _parse_json_list(raw.get("clobTokenIds"))
    outcomes = _parse_json_list(raw.get("outcomes"))
    if not condition_id or not question or len(token_ids) != 2 or len(outcomes) != 2:
        return None
    tokens = (
        Token(token_id=str(token_ids[0]), outcome=str(outcomes[0])),
        Token(token_id=str(token_ids[1]), outcome=str(outcomes[1])),
    )
    try:
        return Market(
            condition_id=str(condition_id),
            question=str(question),
            tokens=tokens,
            tick_size=float(raw.get("orderPriceMinTickSize") or raw.get("minimum_tick_size") or 0.01),
            min_order_size=float(raw.get("orderMinSize") or raw.get("minimum_order_size") or 5.0),
            end_date=_parse_iso(raw.get("endDate")),
            closed=bool(raw.get("closed", False)),
            active=bool(raw.get("active", True)),
        )
    except (TypeError, ValueError):
        return None


def _parse_json_list(raw: object) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _parse_iso(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        # Gamma returns ISO 8601 with a trailing Z.
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
