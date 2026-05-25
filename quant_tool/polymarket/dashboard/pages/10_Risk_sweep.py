"""2-D risk sweep -- find the best (max_per_market, max_total) combination.

Runs the backtest across a grid of risk-limit values and renders a heat-map of
realised PnL so you can see the optimal cap settings at a glance. Constrained:
max_per_market must not exceed max_total, so the upper-left triangle of the
grid is skipped.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quant_tool.polymarket.backtest import run_backtest
from quant_tool.polymarket.dashboard.state import (
    CAPTURE_PATH_KEY,
    get_config,
    init_defaults,
)


st.set_page_config(page_title="Risk sweep", layout="wide")
init_defaults()
st.title("Risk-limit sweep")
st.caption("Find the (max_per_market, max_total) combination that maximises "
            "realised PnL on the current capture.")

cap = st.session_state.get(CAPTURE_PATH_KEY)
if not cap or not Path(cap).exists():
    st.info("Set a capture file on the **Overview** page first "
             "(or click **Generate capture now** in the sidebar).")
    st.stop()

# Show capture stats up front so the user knows what they're sweeping over.
cap_path = Path(cap)
size_mb = cap_path.stat().st_size / (1024 * 1024)
try:
    from quant_tool.polymarket.data.snapshots import iter_batches as _iter
    n_batches = sum(1 for _ in _iter(cap_path))
except Exception:  # noqa: BLE001
    n_batches = -1
i1, i2, i3 = st.columns(3)
i1.metric("Capture file", cap_path.name)
i2.metric("Size", f"{size_mb:.1f} MB")
i3.metric("Batches", n_batches if n_batches >= 0 else "—")

if n_batches > 200:
    st.warning(
        f"Capture has {n_batches} batches — replaying it 225 times will be "
        "slow on a small machine. Consider lowering grid resolution below "
        "to 10×10 first, or cap the replay length."
    )

st.markdown("### Grid")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Max per market** (% of bankroll)")
    pm_lo = st.number_input("PM min", 0.005, 0.50, 0.005, 0.005, format="%.3f")
    pm_hi = st.number_input("PM max", 0.005, 0.50, 0.100, 0.005, format="%.3f")
    pm_n = st.slider("PM points", 5, 30, 15, key="pm_n")
with c2:
    st.markdown("**Max total exposure** (% of bankroll)")
    mt_lo = st.number_input("MT min", 0.05, 5.0, 0.05, 0.05, format="%.2f")
    mt_hi = st.number_input("MT max", 0.05, 5.0, 1.00, 0.05, format="%.2f")
    mt_n = st.slider("MT points", 5, 30, 15, key="mt_n")

pm_values = np.linspace(pm_lo, pm_hi, pm_n)
mt_values = np.linspace(mt_lo, mt_hi, mt_n)
valid_pairs = [(pm, mt) for pm in pm_values for mt in mt_values if pm <= mt]
total = len(valid_pairs)
st.write(f"Will run **{total}** backtests "
         f"({pm_n}×{mt_n} grid, {pm_n*mt_n - total} invalid pairs skipped).")

if total > 900:
    st.warning("That's more than 900 backtests -- consider reducing grid "
                "resolution; this page will block your browser for a while.")

if not st.button("Run sweep", type="primary"):
    st.stop()

base_cfg = get_config()
results: list[dict] = []
progress = st.progress(0.0)

for i, (pm, mt) in enumerate(valid_pairs, 1):
    try:
        r = run_backtest(
            cap,
            strategy_names=base_cfg.enabled,
            bankroll=base_cfg.bankroll,
            max_per_market=float(pm),
            max_total=float(mt),
            strategy_overrides=base_cfg.params,
        )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"({pm:.3f}, {mt:.2f}) failed: {exc}")
        continue
    results.append({
        "max_per_market": float(pm),
        "max_total": float(mt),
        "realised_pnl": r.realised_pnl,
        "final_equity": r.final_equity,
        "max_dd_%": r.max_drawdown * 100,
        "total_fills": sum(s.immediate_fills + s.rested_fills
                            for s in r.stats_by_strategy.values()),
    })
    progress.progress(i / total, text=f"Backtest {i}/{total}")
progress.empty()

if not results:
    st.error("No successful backtests.")
    st.stop()

df = pd.DataFrame(results)

# ----- Heatmap of realised PnL --------------------------------------------
st.subheader("Realised PnL ($) by risk-cap combination")
pivot = df.pivot_table(index="max_per_market", columns="max_total",
                        values="realised_pnl", aggfunc="first")
fig = go.Figure(data=go.Heatmap(
    z=pivot.values,
    x=[f"{c*100:.0f}%" for c in pivot.columns],
    y=[f"{r*100:.1f}%" for r in pivot.index],
    colorscale="RdYlGn", zmid=0,
    colorbar=dict(title="Realised PnL ($)"),
    hovertemplate="max_per_market=%{y}<br>max_total=%{x}<br>PnL=$%{z:.2f}<extra></extra>",
))
fig.update_layout(height=500, margin=dict(l=10, r=10, t=10, b=10),
                   xaxis_title="Max total exposure", yaxis_title="Max per market",
                   xaxis=dict(side="bottom"))
st.plotly_chart(fig, use_container_width=True)

# ----- Best cell ----------------------------------------------------------
best = df.loc[df["realised_pnl"].idxmax()]
st.success(
    f"**Best combination found:**\n\n"
    f"- `max_per_market` = **{best['max_per_market']:.3f}**  ({best['max_per_market']*100:.1f}% of bankroll)\n"
    f"- `max_total`      = **{best['max_total']:.2f}**  ({best['max_total']*100:.0f}% of bankroll)\n"
    f"- Realised PnL = **${best['realised_pnl']:+.2f}**\n"
    f"- Final equity = **${best['final_equity']:,.2f}**\n"
    f"- Max drawdown = **{best['max_dd_%']:.2f}%**\n"
    f"- Total fills = **{int(best['total_fills'])}**"
)

st.markdown("### Apply to the live bot")
st.code(
    f"fly secrets set \\\n"
    f"    BOT_MAX_PER_MARKET={best['max_per_market']:.3f} \\\n"
    f"    BOT_MAX_TOTAL={best['max_total']:.2f} \\\n"
    f"    --app tae-polymarket-bot",
    language="bash",
)
st.caption("Run this in your terminal to push the optimal values. Fly.io will "
            "restart the bot with the new caps within ~30 seconds.")

st.markdown("### Full grid")
st.dataframe(df.sort_values("realised_pnl", ascending=False),
              use_container_width=True, hide_index=True)
