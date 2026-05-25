"""Shared helpers and session-state keys for the Streamlit pages.

All pages read inputs through these helpers so the keys aren't duplicated as
magic strings across files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from quant_tool.polymarket.backtest import BacktestResult, run_backtest
from quant_tool.polymarket.strategy import STRATEGY_REGISTRY


CAPTURE_PATH_KEY = "capture_path"
BACKTEST_KEY = "backtest_result"
PARAMS_KEY = "strategy_params"
ENABLED_KEY = "enabled_strategies"
BANKROLL_KEY = "bankroll"
RISK_PER_MARKET_KEY = "risk_per_market"
RISK_TOTAL_KEY = "risk_total"


@dataclass
class DashboardConfig:
    capture_path: Path | None
    enabled: tuple[str, ...]
    params: dict[str, dict]
    bankroll: float
    max_per_market: float
    max_total: float


def init_defaults() -> None:
    """Populate session_state with sane defaults the first time the app loads."""
    if PARAMS_KEY not in st.session_state:
        st.session_state[PARAMS_KEY] = {name: {} for name in STRATEGY_REGISTRY}
    if ENABLED_KEY not in st.session_state:
        st.session_state[ENABLED_KEY] = tuple(STRATEGY_REGISTRY)
    if BANKROLL_KEY not in st.session_state:
        st.session_state[BANKROLL_KEY] = 10_000.0
    if RISK_PER_MARKET_KEY not in st.session_state:
        st.session_state[RISK_PER_MARKET_KEY] = 0.02
    if RISK_TOTAL_KEY not in st.session_state:
        st.session_state[RISK_TOTAL_KEY] = 0.50


def get_config() -> DashboardConfig:
    init_defaults()
    return DashboardConfig(
        capture_path=st.session_state.get(CAPTURE_PATH_KEY),
        enabled=tuple(st.session_state[ENABLED_KEY]),
        params=dict(st.session_state[PARAMS_KEY]),
        bankroll=float(st.session_state[BANKROLL_KEY]),
        max_per_market=float(st.session_state[RISK_PER_MARKET_KEY]),
        max_total=float(st.session_state[RISK_TOTAL_KEY]),
    )


def run_and_cache_backtest(
    cfg: DashboardConfig,
    *,
    max_batches: int | None = None,
    progress_callback=None,
) -> BacktestResult | None:
    """Run the backtest and stash the result in session_state.

    ``max_batches`` caps how many of the most recent batches are replayed,
    so a 6-hour capture doesn't OOM the Fly machine. ``progress_callback``
    is forwarded to :func:`run_backtest` for the dashboard's progress bar.
    """
    if cfg.capture_path is None or not Path(cfg.capture_path).exists():
        return None
    # Wipe any previous result so a stale chart isn't shown if this run fails,
    # and force a GC sweep so the previous result's fills/positions are freed
    # before we allocate the new run. Otherwise the second click is slow due
    # to memory pressure on the 512MB Fly machine.
    st.session_state.pop(BACKTEST_KEY, None)
    import gc
    gc.collect()
    result = run_backtest(
        cfg.capture_path,
        strategy_names=cfg.enabled,
        bankroll=cfg.bankroll,
        max_per_market=cfg.max_per_market,
        max_total=cfg.max_total,
        strategy_overrides=cfg.params,
        max_batches=max_batches,
        progress_callback=progress_callback,
    )
    st.session_state[BACKTEST_KEY] = result
    return result


def get_cached_backtest() -> BacktestResult | None:
    return st.session_state.get(BACKTEST_KEY)


def require_backtest() -> BacktestResult:
    """Show an info message and stop the page if no backtest has been run."""
    result = get_cached_backtest()
    if result is None:
        st.info("Load a capture file on the **Overview** page first.")
        st.stop()
    return result  # type: ignore[return-value]
