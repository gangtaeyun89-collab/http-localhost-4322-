"""Pre-trade risk checks.

The gate enforces three hard limits:
    * per-market notional cap
    * total open notional cap
    * daily realised + unrealised loss kill switch

A blocked intent is dropped silently; the runner logs the reason. This module
is deliberately stateless across reruns -- the runner restores ``positions``
from the broker on startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum

from quant_tool.polymarket.config import RiskLimits
from quant_tool.polymarket.strategy.base import Intent, Side


class RiskDecision(str, Enum):
    APPROVED = "approved"
    BLOCKED_PER_MARKET = "blocked_per_market"
    BLOCKED_TOTAL = "blocked_total"
    BLOCKED_DAILY_LOSS = "blocked_daily_loss"
    BLOCKED_BAD_PRICE = "blocked_bad_price"


@dataclass
class RiskGate:
    limits: RiskLimits
    starting_equity: float
    _equity: float = 0.0
    _kill_day: date | None = None
    # condition_id -> signed notional (BUY positive, SELL negative)
    _market_exposure: dict[str, float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._equity = self.starting_equity
        self._market_exposure = {}

    def update_equity(self, equity: float, now: datetime | None = None) -> None:
        self._equity = equity
        today = (now or datetime.now(timezone.utc)).date()
        drawdown = (self.starting_equity - equity) / self.starting_equity
        if drawdown >= self.limits.daily_loss_kill:
            self._kill_day = today

    def record_fill(self, condition_id: str, side: Side, notional: float) -> None:
        signed = notional if side is Side.BUY else -notional
        self._market_exposure[condition_id] = self._market_exposure.get(condition_id, 0.0) + signed

    def evaluate(self, intent: Intent, condition_id: str, now: datetime | None = None) -> RiskDecision:
        today = (now or datetime.now(timezone.utc)).date()
        if self._kill_day == today:
            return RiskDecision.BLOCKED_DAILY_LOSS
        if not 0 < intent.price < 1:
            return RiskDecision.BLOCKED_BAD_PRICE

        bankroll = self.limits.bankroll
        market_cap = self.limits.max_position_per_market * bankroll
        projected_market = abs(self._market_exposure.get(condition_id, 0.0)) + intent.notional
        if projected_market > market_cap:
            return RiskDecision.BLOCKED_PER_MARKET

        total_cap = self.limits.max_total_exposure * bankroll
        projected_total = sum(abs(v) for v in self._market_exposure.values()) + intent.notional
        if projected_total > total_cap:
            return RiskDecision.BLOCKED_TOTAL

        return RiskDecision.APPROVED
