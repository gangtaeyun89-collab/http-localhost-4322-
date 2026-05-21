"""Performance and trade-level metrics.

Headline numbers (Sharpe, CAGR) describe the equity curve; the trade-level
stats describe behaviour (how often it trades, how long it holds, hit rate).
Both matter: a strong Sharpe built on three trades is not a strategy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sharpe_ratio(returns: pd.Series, bars_per_year: int) -> float:
    """Annualised Sharpe ratio of a per-bar return series (risk-free = 0)."""
    r = returns.dropna()
    if len(r) < 2 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(bars_per_year))


def max_drawdown(equity: pd.Series) -> float:
    """Largest peak-to-trough decline of an equity curve, as a fraction."""
    e = equity.dropna()
    if e.empty:
        return 0.0
    return float((e / e.cummax() - 1.0).min())


def cagr(equity: pd.Series, bars_per_year: int) -> float:
    """Compound annual growth rate implied by an equity curve."""
    e = equity.dropna()
    if len(e) < 2 or e.iloc[0] <= 0:
        return 0.0
    years = len(e) / bars_per_year
    if years <= 0:
        return 0.0
    return float((e.iloc[-1] / e.iloc[0]) ** (1.0 / years) - 1.0)


def trade_stats(held_position: pd.Series, net_return: pd.Series) -> dict:
    """Segment the held-position series into trades and summarise them.

    A trade is a maximal run of bars holding the same non-zero position sign.
    Returns trade count, win rate, average trade return and average holding.
    """
    pos = held_position.to_numpy()
    ret = net_return.to_numpy()
    sign = np.sign(pos)

    trades: list[float] = []
    holding: list[int] = []
    current_pnl = 0.0
    current_len = 0
    current_sign = 0

    for s, r in zip(sign, ret):
        if s != current_sign:
            if current_sign != 0:
                trades.append(current_pnl)
                holding.append(current_len)
            current_pnl = 0.0
            current_len = 0
            current_sign = s
        if current_sign != 0:
            current_pnl += r
            current_len += 1
    if current_sign != 0:
        trades.append(current_pnl)
        holding.append(current_len)

    if not trades:
        return {
            "n_trades": 0,
            "win_rate": 0.0,
            "avg_trade_return": 0.0,
            "avg_holding_bars": 0.0,
        }

    trades_arr = np.array(trades)
    return {
        "n_trades": len(trades),
        "win_rate": float((trades_arr > 0).mean()),
        "avg_trade_return": float(trades_arr.mean()),
        "avg_holding_bars": float(np.mean(holding)),
    }


def performance_summary(
    net_return: pd.Series,
    equity: pd.Series,
    held_position: pd.Series,
    bars_per_year: int,
) -> dict:
    """Bundle every headline and trade-level metric into one dict."""
    summary = {
        "bars": int(len(net_return)),
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1.0)
        if len(equity) > 1
        else 0.0,
        "cagr": cagr(equity, bars_per_year),
        "sharpe": sharpe_ratio(net_return, bars_per_year),
        "max_drawdown": max_drawdown(equity),
        "annual_volatility": float(net_return.std() * np.sqrt(bars_per_year)),
    }
    summary.update(trade_stats(held_position, net_return))
    return summary
