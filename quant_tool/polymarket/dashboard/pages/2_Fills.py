import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

"""Fills feed -- every simulated fill from the last backtest, searchable."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from quant_tool.polymarket.dashboard.state import require_backtest


st.set_page_config(page_title="Fills", layout="wide")
st.title("Fills")
st.caption("Every simulated fill from the last backtest run.")

result = require_backtest()

if not result.fills:
    st.warning("No fills produced. Either no strategies fired, or no quotes were "
               "ever crossed in this capture. Try widening parameters on the "
               "**Strategies** page, or capture a more volatile window.")
    st.stop()

df = pd.DataFrame([{
    "Time": f.timestamp.isoformat(),
    "Strategy": f.strategy,
    "Token": f.token_id[:14] + "...",
    "Side": f.side.value,
    "Price": f.price,
    "Size": f.size,
    "Notional ($)": round(f.price * f.size, 2),
} for f in result.fills])

# Filters
c1, c2, c3 = st.columns(3)
strategies = sorted(df["Strategy"].unique())
selected = c1.multiselect("Strategy", strategies, default=strategies)
side = c2.selectbox("Side", ["All", "BUY", "SELL"])
min_notional = c3.number_input("Min notional ($)", min_value=0.0, value=0.0, step=10.0)

filtered = df[df["Strategy"].isin(selected)]
if side != "All":
    filtered = filtered[filtered["Side"] == side]
filtered = filtered[filtered["Notional ($)"] >= min_notional]

st.subheader(f"{len(filtered)} fills ({len(df)} total)")
total_notional = filtered["Notional ($)"].sum()
st.caption(f"Total notional traded: **${total_notional:,.2f}**")

st.dataframe(filtered, use_container_width=True, hide_index=True, height=600)
