"""Weekly portfolio report -- the recommend-mode "analyst".

Honest scope: this does **not** predict the market or pick winning trades. It
monitors a portfolio against its target sleeves and reports three factual
things -- how far each sleeve has drifted, the rebalancing trades that would
correct it, and plain risk observations. You read it and decide; it never
trades for you.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_tool.allocation.construction import rebalancing_trades


@dataclass(frozen=True)
class Sleeve:
    """A named target portfolio for one goal / horizon.

    ``targets`` maps asset to weight; it need not be pre-normalised.
    """

    name: str
    targets: pd.Series
    note: str = ""


@dataclass(frozen=True)
class SleeveReport:
    """Per-sleeve section of the report."""

    name: str
    note: str
    value: float
    current_weights: pd.Series
    target_weights: pd.Series
    drift: pd.Series
    max_drift: float
    action: str  # "REBALANCE" or "HOLD"
    trades: pd.Series  # recommended dollar trades (signed; + buy, - sell)


@dataclass(frozen=True)
class PortfolioReport:
    """The full weekly report."""

    sleeves: list[SleeveReport]
    risk_flags: list[str]
    rebalance_band: float

    def render(self) -> str:
        """Render the report as readable text."""
        lines = ["WEEKLY PORTFOLIO REPORT", "=" * 48]
        for s in self.sleeves:
            lines.append("")
            header = f"{s.name}  (${s.value:,.0f})"
            lines.append(header + (f"  -- {s.note}" if s.note else ""))
            for asset in s.target_weights.index:
                cur = s.current_weights.get(asset, 0.0)
                tgt = s.target_weights.get(asset, 0.0)
                lines.append(
                    f"   {asset:<8} current {cur:>6.1%}   target {tgt:>6.1%}"
                    f"   drift {s.drift.get(asset, 0.0):+.1%}"
                )
            if s.action == "REBALANCE":
                lines.append(f"   -> REBALANCE (max drift {s.max_drift:.1%}):")
                for asset, amount in s.trades.items():
                    if abs(amount) >= 1.0:
                        verb = "BUY " if amount > 0 else "SELL"
                        lines.append(f"        {verb} {asset:<8} ${abs(amount):,.0f}")
            else:
                lines.append(
                    f"   -> HOLD (max drift {s.max_drift:.1%}, within "
                    f"{self.rebalance_band:.0%} band)"
                )

        lines.append("")
        lines.append("RISK FLAGS")
        if self.risk_flags:
            for flag in self.risk_flags:
                lines.append(f"   - {flag}")
        else:
            lines.append("   - none")

        lines.append("")
        lines.append("=" * 48)
        lines.append(
            "Mechanical rebalancing recommendations -- you approve or skip. "
            "This report does not predict markets."
        )
        return "\n".join(lines)


def _risk_flags(
    prices: pd.DataFrame,
    drawdown_threshold: float = 0.10,
    vol_ratio: float = 1.5,
) -> list[str]:
    """Factual risk observations per asset: drawdown depth and volatility."""
    flags: list[str] = []
    for asset in prices.columns:
        series = prices[asset].dropna()
        if len(series) < 60:
            continue
        drawdown = series.iloc[-1] / series.tail(252).max() - 1.0
        if drawdown < -drawdown_threshold:
            flags.append(f"{asset} is {abs(drawdown):.0%} below its 1-year high")
        returns = np.log(series).diff().dropna()
        recent = returns.tail(21).std()
        baseline = returns.tail(252).std()
        if baseline > 0 and recent > vol_ratio * baseline:
            flags.append(
                f"{asset} volatility is elevated "
                f"({recent / baseline:.1f}x its 1-year norm)"
            )
    return flags


def build_report(
    sleeves: list[Sleeve],
    holdings: dict[str, pd.Series],
    prices: pd.DataFrame | None = None,
    rebalance_band: float = 0.05,
) -> PortfolioReport:
    """Compare current holdings against the sleeve targets and report.

    Parameters
    ----------
    sleeves:
        The target sleeves.
    holdings:
        Maps sleeve name to a Series of current dollar value per asset (use a
        ``CASH`` entry for un-invested money).
    prices:
        Recent price history per asset, for the risk flags. Optional.
    rebalance_band:
        A sleeve is only flagged to rebalance once its largest per-asset weight
        drift exceeds this band -- so tiny drifts do not churn the portfolio.
    """
    reports: list[SleeveReport] = []
    for sleeve in sleeves:
        held = holdings.get(sleeve.name)
        if held is None or float(held.sum()) <= 0:
            continue
        value = float(held.sum())
        assets = held.index.union(sleeve.targets.index)
        held = held.reindex(assets).fillna(0.0)
        target = sleeve.targets.reindex(assets).fillna(0.0)
        target = target / target.sum()
        current = held / value
        drift = current - target
        max_drift = float(drift.abs().max())

        if max_drift > rebalance_band:
            action = "REBALANCE"
            trades = rebalancing_trades(held, target)
        else:
            action = "HOLD"
            trades = pd.Series(0.0, index=assets)

        reports.append(
            SleeveReport(
                name=sleeve.name,
                note=sleeve.note,
                value=value,
                current_weights=current,
                target_weights=target,
                drift=drift,
                max_drift=max_drift,
                action=action,
                trades=trades,
            )
        )

    flags = _risk_flags(prices) if prices is not None else []
    return PortfolioReport(reports, flags, rebalance_band)
