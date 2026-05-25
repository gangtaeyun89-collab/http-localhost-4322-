"""Backtest a regime-driven position-management rule.

The rule is deliberately simple so the question being answered is clean:
*does acting on the HMM/BOCPD signal beat buy-and-hold, net of trading
costs, on this name?*  If the answer is no, no amount of downstream
engineering matters.

Position weights are a lookup table on the action label:

    HOLD    -> 1.0   (fully invested)
    TRIM    -> 0.5   (half position)
    REDUCE  -> 0.0   (flat)

Timing convention matches ``quant_tool.backtest.engine``:

* the signal computed at the close of bar ``t`` sets the *target* weight
  for ``t``;
* the weight carried *into* bar ``t`` -- the one earning bar ``t``'s
  return -- is the target set at ``t - 1`` (one-bar execution lag);
* trading costs are charged on the change in weight at bar ``t``.

This eliminates look-ahead by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_tool.backtest.metrics import performance_summary
from quant_tool.regime.signals import HOLD, REDUCE, TRIM


DEFAULT_WEIGHTS = {HOLD: 1.0, TRIM: 0.5, REDUCE: 0.0}


@dataclass(frozen=True)
class RegimeBacktestResult:
    bars: pd.DataFrame
    stats: dict
    benchmark_stats: dict

    def describe(self) -> str:
        s, b = self.stats, self.benchmark_stats
        return (
            f"{'metric':<20}{'regime':>14}{'buy & hold':>14}\n"
            f"{'-'*48}\n"
            f"{'bars':<20}{s['bars']:>14d}{b['bars']:>14d}\n"
            f"{'total return':<20}{s['total_return']:>13.2%}{b['total_return']:>14.2%}\n"
            f"{'CAGR':<20}{s['cagr']:>13.2%}{b['cagr']:>14.2%}\n"
            f"{'Sharpe':<20}{s['sharpe']:>14.2f}{b['sharpe']:>14.2f}\n"
            f"{'annual vol':<20}{s['annual_volatility']:>13.2%}{b['annual_volatility']:>14.2%}\n"
            f"{'max drawdown':<20}{s['max_drawdown']:>13.2%}{b['max_drawdown']:>14.2%}\n"
            f"{'time invested':<20}{s.get('time_invested', 1.0):>13.2%}{1.0:>14.2%}\n"
            f"{'turnover (annual)':<20}{s.get('annual_turnover', 0):>14.2f}{0:>14.2f}\n"
            f"{'n trades':<20}{s['n_trades']:>14d}{0:>14d}\n"
        )


def run_regime_backtest(
    close: pd.Series,
    signals: pd.DataFrame,
    weights: dict[str, float] | None = None,
    cost_bps: float = 25.0,
    bars_per_year: int = 252,
) -> RegimeBacktestResult:
    """Backtest the HOLD/TRIM/REDUCE rule against buy-and-hold.

    Parameters
    ----------
    close:
        Adjusted close prices, datetime-indexed.
    signals:
        Output of :func:`generate_signals` -- must contain an ``action``
        column with values in ``{HOLD, TRIM, REDUCE}``.
    weights:
        Mapping from action label to portfolio weight.  Defaults to
        ``{HOLD: 1.0, TRIM: 0.5, REDUCE: 0.0}``.
    cost_bps:
        Round-trip cost in basis points charged on the absolute change in
        weight each bar.  KRX retail is roughly 23 bps round-trip after
        the securities transaction tax; 25 is a slightly conservative
        default.
    bars_per_year:
        Annualisation factor (252 for daily KRX bars).
    """
    weights = weights or DEFAULT_WEIGHTS
    close = close.astype(float).sort_index()

    aligned = signals.reindex(close.index).ffill()
    target = aligned["action"].map(weights).astype(float)
    target = target.fillna(weights[HOLD])

    held = target.shift(1).fillna(weights[HOLD])
    ret = np.log(close).diff().fillna(0.0)
    turnover = (target - held).abs()
    cost = turnover * (cost_bps / 10_000.0)

    gross_ret = held * ret
    net_ret = gross_ret - cost
    equity = np.exp(net_ret.cumsum())

    bh_ret = ret
    bh_equity = np.exp(bh_ret.cumsum())

    bars = pd.DataFrame(
        {
            "close": close,
            "action": aligned["action"],
            "target_weight": target,
            "held_weight": held,
            "asset_return": ret,
            "gross_return": gross_ret,
            "cost": cost,
            "net_return": net_ret,
            "equity": equity,
            "buy_hold_equity": bh_equity,
        }
    )

    # Treat any non-zero held weight as "in a position" for trade counting.
    position_flag = (held != 0.0).astype(int) * np.sign(held).astype(int)
    stats = performance_summary(net_ret, equity, position_flag, bars_per_year)
    stats["time_invested"] = float((held > 0).mean())
    stats["annual_turnover"] = float(turnover.sum() / (len(turnover) / bars_per_year))

    benchmark_stats = performance_summary(
        bh_ret, bh_equity, pd.Series(1, index=close.index), bars_per_year
    )

    return RegimeBacktestResult(bars=bars, stats=stats, benchmark_stats=benchmark_stats)
