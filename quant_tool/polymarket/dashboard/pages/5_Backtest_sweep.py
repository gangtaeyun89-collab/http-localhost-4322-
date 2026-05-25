import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

"""Parameter sweep -- run the backtest across many parameter values, compare."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from quant_tool.polymarket.backtest import run_backtest
from quant_tool.polymarket.dashboard.state import (
    CAPTURE_PATH_KEY,
    get_config,
    init_defaults,
)


st.set_page_config(page_title="Backtest sweep", layout="wide")
init_defaults()
st.title("Backtest sweep")
st.caption("Vary one parameter across a range and compare per-strategy results.")

cap = st.session_state.get(CAPTURE_PATH_KEY)
if not cap:
    st.info("Set a capture file on the **Overview** page first.")
    st.stop()

# Pick which parameter to sweep
SWEEPS = {
    "market_maker / quote_size":          ("market_maker", "quote_size",          (5, 200, 5)),
    "market_maker / min_spread_ticks":    ("market_maker", "min_spread_ticks",    (1, 10, 1)),
    "market_maker / inventory_skew":      ("market_maker", "inventory_skew",      (0.0, 0.01, 0.001)),
    "arb_yes_no / min_edge":              ("arb_yes_no",   "min_edge",            (0.0005, 0.05, 0.001)),
    "arb_yes_no / max_clip_shares":       ("arb_yes_no",   "max_clip_shares",     (10, 500, 10)),
    "signal_model / momentum_threshold":  ("signal_model", "momentum_threshold",  (0.001, 0.05, 0.002)),
    "signal_model / ema_alpha":           ("signal_model", "ema_alpha",           (0.05, 1.0, 0.05)),
}

sweep_key = st.selectbox("Parameter to sweep", list(SWEEPS.keys()))
strategy, param, (lo_default, hi_default, step_default) = SWEEPS[sweep_key]

c1, c2, c3 = st.columns(3)
lo = c1.number_input("From", value=float(lo_default), step=float(step_default), format="%.4f")
hi = c2.number_input("To",   value=float(hi_default), step=float(step_default), format="%.4f")
step = c3.number_input("Step", value=float(step_default), min_value=1e-6, format="%.4f")

# Build the value list
values: list[float] = []
v = lo
while v <= hi + 1e-9:
    values.append(round(v, 6))
    v += step
if len(values) > 50:
    st.warning(f"That's {len(values)} runs -- cap at 50 to keep this fast.")
    values = values[:50]

st.write(f"Will run **{len(values)}** backtests for {strategy}.{param} in {values}")

if st.button("Run sweep", type="primary"):
    base_cfg = get_config()
    rows = []
    progress = st.progress(0.0)
    for i, val in enumerate(values, 1):
        overrides = {s: dict(p) for s, p in base_cfg.params.items()}
        # Coerce to int if the parameter is naturally an integer.
        cast_val = int(val) if param in {"min_spread_ticks"} else val
        overrides.setdefault(strategy, {})[param] = cast_val
        try:
            r = run_backtest(
                cap,
                strategy_names=base_cfg.enabled,
                bankroll=base_cfg.bankroll,
                max_per_market=base_cfg.max_per_market,
                max_total=base_cfg.max_total,
                strategy_overrides=overrides,
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"value={val}: {exc}")
            continue
        st_stat = r.stats_by_strategy.get(strategy)
        rows.append({
            "value": cast_val,
            "final_equity": r.final_equity,
            "realised_pnl": r.realised_pnl,
            "max_dd_%": r.max_drawdown * 100,
            f"{strategy}_intents": st_stat.intents if st_stat else 0,
            f"{strategy}_fills": (st_stat.immediate_fills + st_stat.rested_fills) if st_stat else 0,
            f"{strategy}_notional": st_stat.notional_filled if st_stat else 0,
            f"{strategy}_realised": st_stat.realised_pnl if st_stat else 0,
        })
        progress.progress(i / len(values))
    progress.empty()

    if rows:
        df = pd.DataFrame(rows)
        st.subheader("Sweep results")
        st.dataframe(df, use_container_width=True, hide_index=True)

        fig = px.line(df, x="value", y=["final_equity", "realised_pnl"],
                       title=f"{strategy}.{param} sweep -- equity & realised PnL")
        fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10),
                           xaxis_title=param, yaxis_title="USDC")
        st.plotly_chart(fig, use_container_width=True)

        best = df.loc[df["realised_pnl"].idxmax()]
        st.success(f"Best by realised PnL: **{strategy}.{param} = {best['value']}** "
                    f"→ realised ${best['realised_pnl']:.2f}, equity ${best['final_equity']:.2f}")
