"""Walk-forward backtest service.

Wraps ``quant_tool.backtest.walk_forward`` so the API can drive it from a
small JSON payload. Returns the OOS equity curve plus per-window train/test
Sharpe, which together answer the only two questions a backtest is
allowed to answer: "did the strategy work out of sample?" and "did the
training Sharpe predict it?"
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pandas as pd

from backend.app.schemas import (
    BacktestRequest,
    BacktestResult,
    BacktestStats,
    EquityPoint,
    WindowReport,
)
from backend.app.services.data_source import load_universe, universe_source
from quant_tool.backtest.walk_forward import walk_forward
from quant_tool.config.settings import (
    BacktestConfig,
    CostConfig,
    PairConfig,
    SignalConfig,
)
from quant_tool.data.features import align_prices, infer_bars_per_year
from quant_tool.strategy.pair_finder import cointegration_test


def _safe(value: float | None, default: float = 0.0) -> float:
    if value is None or not math.isfinite(value):
        return default
    return float(value)


def _ts(ts) -> str:
    if hasattr(ts, "strftime"):
        return ts.strftime("%Y-%m-%dT%H:%M:%S")
    return str(ts)


def _downsample(df: pd.DataFrame, max_points: int) -> pd.DataFrame:
    if len(df) <= max_points:
        return df
    step = max(1, len(df) // max_points)
    return df.iloc[::step]


def run_walk_forward(req: BacktestRequest) -> BacktestResult:
    """Execute a walk-forward backtest for the requested pair and config."""
    universe = load_universe()
    if req.base not in universe.columns or req.quote not in universe.columns:
        raise KeyError(f"unknown ticker(s): {req.base}, {req.quote}")

    prices = align_prices(universe[req.base], universe[req.quote])
    if len(prices) < req.train_size + req.test_size:
        raise ValueError(
            f"need at least {req.train_size + req.test_size} aligned bars, "
            f"have {len(prices)}"
        )

    # Cointegration screen feeds two things: the user-facing p-value /
    # half-life on the result, and the tuned z-score lookback when the
    # user asks for it.
    coint = cointegration_test(
        prices["base"], prices["quote"], base_name=req.base, quote_name=req.quote
    )
    half_life = _safe(coint.half_life, 30.0)

    bpy = infer_bars_per_year(prices.index, asset_class=req.asset_class)
    cost = (
        CostConfig.for_crypto()
        if req.asset_class == "crypto"
        else CostConfig.for_us_equity()
    )
    signal = (
        SignalConfig.for_half_life(
            half_life,
            entry_z=req.entry_z,
            exit_z=req.exit_z,
        )
        if req.tune_lookback
        else SignalConfig(
            zscore_lookback=60,
            entry_z=req.entry_z,
            exit_z=req.exit_z,
        )
    )

    config = BacktestConfig(
        pair=PairConfig(base=req.base, quote=req.quote),
        signal=signal,
        cost=cost,
        hedge_method=req.hedge_method,
        bars_per_year=bpy,
        target_volatility=req.target_volatility,
    )

    wf = walk_forward(prices, config, req.train_size, req.test_size)

    # Per-window report
    windows: list[WindowReport] = [
        WindowReport(
            train_start=_ts(w.train_start),
            train_end=_ts(w.train_end),
            test_start=_ts(w.test_start),
            test_end=_ts(w.test_end),
            train_sharpe=_safe(w.train_sharpe),
            test_sharpe=_safe(w.test_sharpe),
        )
        for w in wf.windows
    ]

    # Equity curve. Downsample to keep the payload reasonable; recharts is
    # fine with 1000 points but the wire cost grows linearly.
    bars = _downsample(wf.bars, 800)
    equity = [
        EquityPoint(
            t=_ts(ts),
            equity=_safe(float(bars.at[ts, "equity"])),
            netReturn=_safe(float(bars.at[ts, "net_return"])),
            position=_safe(float(bars.at[ts, "position"])),
        )
        for ts in bars.index
    ]

    stats = BacktestStats(
        sharpe=_safe(wf.stats.get("sharpe")),
        cagr=_safe(wf.stats.get("cagr")),
        maxDrawdown=_safe(wf.stats.get("max_drawdown")),
        totalReturn=_safe(wf.stats.get("total_return")),
        annualVolatility=_safe(wf.stats.get("annual_volatility")),
        winRate=_safe(wf.stats.get("win_rate")),
        nTrades=int(wf.stats.get("n_trades", 0)),
        bars=int(wf.stats.get("bars", len(wf.bars))),
    )

    mean_train = float(np.mean([w.train_sharpe for w in wf.windows])) if windows else 0.0
    mean_test = float(np.mean([w.test_sharpe for w in wf.windows])) if windows else 0.0

    return BacktestResult(
        request=req,
        stats=stats,
        equity=equity,
        windows=windows,
        meanTrainSharpe=_safe(mean_train),
        meanTestSharpe=_safe(mean_test),
        overfitGap=_safe(mean_train - mean_test),
        halfLife=half_life,
        pvalue=_safe(coint.pvalue, 1.0),
        lookbackUsed=signal.zscore_lookback,
        barsPerYear=bpy,
        source=universe_source(),
    )
