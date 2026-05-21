"""Typed configuration objects for the toolkit.

Configuration is kept as plain dataclasses so it is easy to construct in code,
in tests, or from a YAML file via :func:`load_config`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CostConfig:
    """Round-trip trading cost assumptions, expressed in basis points per side.

    Crypto taker fees plus slippage routinely consume most of a mean-reversion
    edge, so these defaults are deliberately conservative.
    """

    taker_fee_bps: float = 6.0
    slippage_bps: float = 2.0
    funding_bps_per_day: float = 0.0

    @property
    def cost_rate(self) -> float:
        """Cost charged per unit of notional traded on one leg (fraction)."""
        return (self.taker_fee_bps + self.slippage_bps) / 1e4


@dataclass(frozen=True)
class SignalConfig:
    """Z-score window and entry/exit thresholds for the spread."""

    zscore_lookback: int = 60
    entry_z: float = 2.0
    exit_z: float = 0.5
    stop_z: float = 4.0

    def __post_init__(self) -> None:
        if self.zscore_lookback < 2:
            raise ValueError("zscore_lookback must be >= 2")
        if not 0 <= self.exit_z < self.entry_z < self.stop_z:
            raise ValueError("require 0 <= exit_z < entry_z < stop_z")


@dataclass(frozen=True)
class PairConfig:
    """A tradable pair: ``base`` is regressed on ``quote``."""

    base: str
    quote: str
    timeframe: str = "1h"

    @property
    def name(self) -> str:
        return f"{self.base} vs {self.quote}"


@dataclass(frozen=True)
class BacktestConfig:
    """Top-level configuration bundle for a backtest run."""

    pair: PairConfig
    signal: SignalConfig = field(default_factory=SignalConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    hedge_method: str = "kalman"  # "ols" or "kalman"
    hedge_lookback: int = 500  # OLS hedge-ratio window; unused by Kalman
    bars_per_year: int = 24 * 365
    initial_capital: float = 10_000.0
    target_volatility: float | None = None  # annualised; None disables sizing
    vol_lookback: int = 100
    max_leverage: float = 3.0

    def __post_init__(self) -> None:
        if self.hedge_method not in {"ols", "kalman"}:
            raise ValueError("hedge_method must be 'ols' or 'kalman'")
        if self.hedge_lookback < 2:
            raise ValueError("hedge_lookback must be >= 2")
        if self.target_volatility is not None and self.target_volatility <= 0:
            raise ValueError("target_volatility must be positive or None")
        if self.max_leverage <= 0:
            raise ValueError("max_leverage must be positive")


def _filter_kwargs(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    allowed = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in allowed}


def load_config(path: str | Path) -> BacktestConfig:
    """Load a :class:`BacktestConfig` from a YAML file.

    Requires ``pyyaml``; the toolkit otherwise runs without it.
    """
    import yaml  # local import keeps yaml an optional dependency

    raw = yaml.safe_load(Path(path).read_text())
    pair = PairConfig(**_filter_kwargs(PairConfig, raw["pair"]))
    signal = SignalConfig(**_filter_kwargs(SignalConfig, raw.get("signal", {})))
    cost = CostConfig(**_filter_kwargs(CostConfig, raw.get("cost", {})))
    top = _filter_kwargs(BacktestConfig, raw)
    top.update(pair=pair, signal=signal, cost=cost)
    return BacktestConfig(**top)
