"""Walk-forward out-of-sample evaluation.

A single backtest over the whole history answers the wrong question: it shows
how a strategy would have done with parameters chosen *with hindsight*.
Walk-forward analysis answers the honest one. The history is cut into
consecutive ``(train, test)`` windows; on each train window the strategy
parameters are chosen by grid search, and that exact choice is then evaluated
on the *following*, unseen test window. Concatenating the test windows yields
an equity curve in which no parameter ever saw its own evaluation data -- the
closest in-sample proxy for live performance.

A persistent gap between train Sharpe and test Sharpe across windows is the
tell-tale sign of overfitting.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, fields, replace
from typing import Any

import pandas as pd

from quant_tool.backtest.engine import run_backtest
from quant_tool.backtest.metrics import performance_summary, sharpe_ratio
from quant_tool.config.settings import BacktestConfig

# Grid keys that belong to the nested SignalConfig rather than BacktestConfig.
_SIGNAL_PARAMS = {"entry_z", "exit_z", "stop_z", "zscore_lookback"}


@dataclass(frozen=True)
class WindowReport:
    """One walk-forward window: parameters chosen on train, scored on test."""

    train_start: Any
    train_end: Any
    test_start: Any
    test_end: Any
    params: dict
    train_sharpe: float
    test_sharpe: float


@dataclass(frozen=True)
class WalkForwardResult:
    """Aggregate out-of-sample result of :func:`walk_forward`.

    bars     stitched test-window bars with a continuous OOS equity curve
    stats    out-of-sample performance summary
    windows  per-window parameter choices and train/test Sharpe
    """

    bars: pd.DataFrame
    stats: dict
    windows: list[WindowReport]

    @property
    def equity(self) -> pd.Series:
        return self.bars["equity"]

    def describe(self) -> str:
        """Human-readable summary, including the overfitting diagnostic."""
        s = self.stats
        n = len(self.windows)
        mean_train = sum(w.train_sharpe for w in self.windows) / n
        mean_test = sum(w.test_sharpe for w in self.windows) / n
        return (
            "Walk-forward out-of-sample result\n"
            f"Windows         {n}\n"
            f"OOS bars        {s['bars']}\n"
            f"Total return    {s['total_return']:+.2%}\n"
            f"CAGR            {s['cagr']:+.2%}\n"
            f"Sharpe          {s['sharpe']:.2f}\n"
            f"Annual vol      {s['annual_volatility']:.2%}\n"
            f"Max drawdown    {s['max_drawdown']:.2%}\n"
            f"Trades          {s['n_trades']}\n"
            f"Win rate        {s['win_rate']:.2%}\n"
            f"Mean train Sharpe   {mean_train:+.2f}\n"
            f"Mean test Sharpe    {mean_test:+.2f}   "
            f"(a large train>test gap means overfitting)"
        )


def _expand_grid(param_grid: dict[str, list]) -> list[dict]:
    """Cartesian product of a parameter grid into a list of combinations."""
    keys = list(param_grid)
    return [
        dict(zip(keys, values))
        for values in itertools.product(*(param_grid[k] for k in keys))
    ]


def _apply_params(config: BacktestConfig, combo: dict) -> BacktestConfig:
    """Return ``config`` with the combo applied (SignalConfig fields nested)."""
    signal_updates = {k: v for k, v in combo.items() if k in _SIGNAL_PARAMS}
    config_updates = {k: v for k, v in combo.items() if k not in _SIGNAL_PARAMS}
    cfg = config
    if signal_updates:
        cfg = replace(cfg, signal=replace(cfg.signal, **signal_updates))
    if config_updates:
        cfg = replace(cfg, **config_updates)
    return cfg


def walk_forward(
    prices: pd.DataFrame,
    config: BacktestConfig,
    train_size: int,
    test_size: int,
    param_grid: dict[str, list] | None = None,
) -> WalkForwardResult:
    """Run a walk-forward evaluation with per-window parameter selection.

    Parameters
    ----------
    prices:
        Base/quote price frame (the input :func:`run_backtest` expects).
    config:
        Base configuration; the grid overrides selected fields per window.
    train_size, test_size:
        Window lengths in bars. Windows tile the history -- each test window
        begins exactly where the previous one ended.
    param_grid:
        Maps a ``BacktestConfig`` or ``SignalConfig`` field to the values to
        try, e.g. ``{"entry_z": [1.0, 1.5, 2.0]}``. On each train window the
        combination with the best net Sharpe is chosen and applied to the
        following test window. Defaults to ``{}`` -- no tuning, a pure
        out-of-sample validation of the base config, which is the safe
        default: selecting a parameter on a noisy train-window Sharpe is itself
        a form of overfitting and often *hurts* test performance.
    """
    if train_size < 2 or test_size < 1:
        raise ValueError("train_size must be >= 2 and test_size >= 1")
    n = len(prices)
    if train_size + test_size > n:
        raise ValueError(
            f"need at least train_size + test_size = {train_size + test_size} "
            f"bars, got {n}"
        )

    if param_grid is None:
        param_grid = {}
    valid_keys = {f.name for f in fields(BacktestConfig)} | _SIGNAL_PARAMS
    for key in param_grid:
        if key not in valid_keys:
            raise ValueError(f"unknown param_grid key {key!r}")
    combos = _expand_grid(param_grid)
    if not combos:
        raise ValueError("param_grid produced no combinations")

    windows: list[WindowReport] = []
    oos_frames: list[pd.DataFrame] = []

    start = 0
    while start + train_size + test_size <= n:
        train = prices.iloc[start : start + train_size]
        full = prices.iloc[start : start + train_size + test_size]

        # --- choose parameters on the training window only ---
        best_sharpe = float("-inf")
        best_combo: dict | None = None
        best_cfg: BacktestConfig | None = None
        for combo in combos:
            try:
                cfg = _apply_params(config, combo)
                train_result = run_backtest(train, cfg)
            except ValueError:
                # Invalid combo, or train window too short for the lookbacks.
                continue
            if train_result.stats["sharpe"] > best_sharpe:
                best_sharpe = train_result.stats["sharpe"]
                best_combo = combo
                best_cfg = cfg

        if best_cfg is None:
            start += test_size
            continue

        # --- evaluate the chosen parameters on the unseen test window ---
        # Run on train+test so the test rows get a proper warm-up, then keep
        # only the test rows: the parameters were fixed without seeing them.
        full_result = run_backtest(full, best_cfg)
        test_bars = full_result.bars.iloc[train_size:].copy()
        oos_frames.append(test_bars)
        windows.append(
            WindowReport(
                train_start=prices.index[start],
                train_end=prices.index[start + train_size - 1],
                test_start=prices.index[start + train_size],
                test_end=prices.index[start + train_size + test_size - 1],
                params=dict(best_combo),
                train_sharpe=float(best_sharpe),
                test_sharpe=sharpe_ratio(
                    test_bars["net_return"], config.bars_per_year
                ),
            )
        )
        start += test_size

    if not oos_frames:
        raise ValueError(
            "no walk-forward window could be evaluated; train_size is likely "
            "too small for the configured hedge/z-score lookbacks"
        )

    # --- stitch the test windows into one continuous OOS equity curve ---
    # Consecutive test windows tile the timeline, so concatenation is gap-free.
    # Each window is a separate backtest run, so a position open across a
    # window boundary is re-established rather than carried -- a small,
    # conservative artifact inherent to walk-forward analysis.
    oos = pd.concat(oos_frames)
    oos["equity"] = config.initial_capital * (1.0 + oos["net_return"]).cumprod()
    stats = performance_summary(
        oos["net_return"], oos["equity"], oos["position"], config.bars_per_year
    )
    return WalkForwardResult(bars=oos, stats=stats, windows=windows)
