"""Polymarket subsystem configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RiskLimits:
    """Hard limits enforced by :class:`quant_tool.polymarket.risk.RiskGate`.

    Sizes are fractions of ``bankroll``. ``max_position_per_market`` applies to
    *net* notional per market (YES long minus NO long, in USDC). ``daily_loss_kill``
    is a one-way switch: once tripped, the gate blocks all new orders for the rest
    of the UTC day.
    """

    bankroll: float = 10_000.0
    max_position_per_market: float = 0.02
    max_total_exposure: float = 0.50
    daily_loss_kill: float = 0.05
    min_edge_bps: float = 50.0  # strategies should reject quotes thinner than this

    def __post_init__(self) -> None:
        if self.bankroll <= 0:
            raise ValueError("bankroll must be positive")
        for name, value in (
            ("max_position_per_market", self.max_position_per_market),
            ("max_total_exposure", self.max_total_exposure),
            ("daily_loss_kill", self.daily_loss_kill),
        ):
            if not 0 < value <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        if self.max_position_per_market > self.max_total_exposure:
            raise ValueError("max_position_per_market cannot exceed max_total_exposure")
        if self.min_edge_bps < 0:
            raise ValueError("min_edge_bps must be non-negative")


@dataclass(frozen=True)
class PolymarketConfig:
    """Top-level config for the Polymarket runner.

    ``mode`` switches the order router between simulation and live trading.
    Strategy names listed in ``strategies`` are looked up in the strategy
    registry; unknown names raise at startup.
    """

    mode: str = "paper"  # "paper" or "live"
    strategies: tuple[str, ...] = ("market_maker", "arb_yes_no", "copy_trader", "signal_model")
    bake_off_days: int = 5
    poll_interval_seconds: float = 2.0
    market_universe_refresh_minutes: int = 10
    risk: RiskLimits = field(default_factory=RiskLimits)

    # Endpoints -- overridable for testing; sensible Polymarket defaults otherwise.
    clob_base_url: str = "https://clob.polymarket.com"
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    clob_ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/"

    def __post_init__(self) -> None:
        if self.mode not in {"paper", "live"}:
            raise ValueError("mode must be 'paper' or 'live'")
        if not self.strategies:
            raise ValueError("at least one strategy must be enabled")
        if self.bake_off_days <= 0:
            raise ValueError("bake_off_days must be positive")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if self.market_universe_refresh_minutes <= 0:
            raise ValueError("market_universe_refresh_minutes must be positive")
