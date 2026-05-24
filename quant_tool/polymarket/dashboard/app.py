"""Polymarket bake-off ops console -- entry point.

Run from the repo root with:

    streamlit run quant_tool/polymarket/dashboard/app.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quant_tool.polymarket import load_dotenv
from quant_tool.polymarket.dashboard.state import (
    BACKTEST_KEY,
    CAPTURE_PATH_KEY,
    get_config,
    init_defaults,
    run_and_cache_backtest,
)


st.set_page_config(page_title="Polymarket Bot", page_icon=None, layout="wide")
load_dotenv()
init_defaults()

st.title("Polymarket bake-off")
st.caption("Local ops console -- read-only view of captured snapshots + paper-trade replays.")

# ---------- Sidebar: capture file + risk knobs ----------
with st.sidebar:
    st.header("Capture file")
    text_path = st.text_input("Path to JSONL capture",
                              value=str(st.session_state.get(CAPTURE_PATH_KEY, "")),
                              help="Path to a file produced by scripts/polymarket_capture.py")
    uploaded = st.file_uploader("...or upload one", type=["jsonl"])
    if uploaded is not None:
        target = Path(".dashboard_uploads")
        target.mkdir(exist_ok=True)
        dest = target / uploaded.name
        dest.write_bytes(uploaded.getbuffer())
        text_path = str(dest)
    if text_path:
        st.session_state[CAPTURE_PATH_KEY] = text_path

    st.header("Risk")
    st.session_state["bankroll"] = st.number_input("Bankroll (USDC)",
                                                    min_value=100.0, value=float(st.session_state["bankroll"]),
                                                    step=100.0)
    st.session_state["risk_per_market"] = st.slider("Max per market (% of bankroll)",
                                                     min_value=0.005, max_value=0.20,
                                                     value=float(st.session_state["risk_per_market"]),
                                                     step=0.005, format="%.3f")
    st.session_state["risk_total"] = st.slider("Max total exposure (% of bankroll)",
                                                min_value=0.05, max_value=1.00,
                                                value=float(st.session_state["risk_total"]),
                                                step=0.05, format="%.2f")

    if st.button("Run backtest", type="primary", use_container_width=True):
        with st.spinner("Replaying capture..."):
            cfg = get_config()
            result = run_and_cache_backtest(cfg)
        if result is None:
            st.error("No capture file selected or path doesn't exist.")
        else:
            st.success(f"Replayed {result.batches} batches.")

# ---------- Main panel ----------
result = st.session_state.get(BACKTEST_KEY)

if result is None:
    st.info("Enter a capture file path in the sidebar and click **Run backtest** to begin.")
    st.markdown("""
    ### Quick start
    1. On your laptop, run:
       ```bash
       PYTHONPATH=. python scripts/polymarket_capture.py \\
           --output capture.jsonl --interval 60 --duration 3600 --markets 30
       ```
    2. Copy `capture.jsonl` to this machine and enter its path in the sidebar.
    3. Click **Run backtest**.

    Then explore the **Strategies**, **Fills**, **Markets**, and **Backtest sweep** pages.
    """)
    st.stop()

# ----- Top-row KPIs -----
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Final equity", f"${result.final_equity:,.2f}",
            delta=f"${result.final_equity - result.starting_equity:+,.2f}")
col2.metric("Realised PnL", f"${result.realised_pnl:+,.2f}")
col3.metric("Peak equity", f"${result.peak_equity:,.2f}")
col4.metric("Max drawdown", f"{result.max_drawdown*100:.2f}%")
total_fills = sum(s.immediate_fills + s.rested_fills for s in result.stats_by_strategy.values())
col5.metric("Total fills", f"{total_fills}")

st.divider()

# ----- Equity curve -----
st.subheader("Equity curve")
if result.equity_curve:
    df = pd.DataFrame([{"t": p.timestamp, "equity": p.equity, "realised": p.realised_pnl}
                       for p in result.equity_curve])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["t"], y=df["equity"], name="Equity",
                              line=dict(color="#1f77b4", width=2)))
    fig.add_trace(go.Scatter(x=df["t"], y=df["realised"] + result.starting_equity,
                              name="Realised (offset)", line=dict(color="#2ca02c", width=1, dash="dot")))
    fig.add_hline(y=result.starting_equity, line_dash="dash", line_color="gray",
                   annotation_text="Starting equity")
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                       xaxis_title=None, yaxis_title="USDC", legend=dict(orientation="h", y=1.05))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("No equity points -- the capture has no batches.")

# ----- Per-strategy summary -----
st.subheader("Per-strategy attribution")
rows = []
for s in result.stats_by_strategy.values():
    total_filled = s.immediate_fills + s.rested_fills
    fill_rate = (total_filled / s.intents * 100) if s.intents else 0.0
    rows.append({
        "Strategy": s.name,
        "Intents": s.intents,
        "Blocked": s.blocked,
        "Taker fills": s.immediate_fills,
        "Maker fills": s.rested_fills,
        "Fill rate %": round(fill_rate, 1),
        "Notional ($)": round(s.notional_filled, 2),
        "Realised PnL ($)": round(s.realised_pnl, 2),
    })
strategy_df = pd.DataFrame(rows)
st.dataframe(strategy_df, use_container_width=True, hide_index=True)

# ----- Capture metadata -----
st.subheader("Capture")
cap_path = st.session_state.get(CAPTURE_PATH_KEY, "")
m1, m2, m3 = st.columns(3)
m1.metric("Batches replayed", result.batches)
m2.metric("Snapshots seen", result.snapshots)
m3.metric("Trade prints", result.prints_seen,
          help="If 0, fill detection falls back to book-change matching (less accurate).")
st.caption(f"Source: `{cap_path}`")
