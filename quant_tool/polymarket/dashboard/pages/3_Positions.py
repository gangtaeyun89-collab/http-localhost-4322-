"""Open positions and per-token realised PnL from the last backtest."""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import pandas as pd
import streamlit as st

from quant_tool.polymarket.dashboard.state import require_backtest


st.set_page_config(page_title="Positions", layout="wide")
st.title("Positions")

result = require_backtest()

rows = []
for token_id, pos in result.positions.items():
    rows.append({
        "Token": token_id[:14] + "...",
        "Shares": round(pos.shares, 2),
        "Avg cost": round(pos.avg_price, 4) if pos.avg_price else None,
        "Realised PnL ($)": round(pos.realised_pnl, 2),
        "Direction": "LONG" if pos.shares > 0 else "SHORT" if pos.shares < 0 else "FLAT",
    })

if not rows:
    st.warning("No positions yet -- no fills happened in this backtest.")
    st.stop()

df = pd.DataFrame(rows).sort_values("Realised PnL ($)", ascending=False)
open_only = st.checkbox("Show only open positions", value=False)
if open_only:
    df = df[df["Shares"] != 0]

st.subheader(f"{len(df)} positions")
totals = {
    "Open": (df["Shares"] != 0).sum(),
    "Realised PnL": f"${df['Realised PnL ($)'].sum():,.2f}",
    "Long exposure (shares)": df.loc[df["Shares"] > 0, "Shares"].sum(),
    "Short exposure (shares)": df.loc[df["Shares"] < 0, "Shares"].sum(),
}
c1, c2, c3, c4 = st.columns(4)
c1.metric("Open positions", totals["Open"])
c2.metric("Realised PnL", totals["Realised PnL"])
c3.metric("Long shares", f"{totals['Long exposure (shares)']:.0f}")
c4.metric("Short shares", f"{totals['Short exposure (shares)']:.0f}")

st.dataframe(df, use_container_width=True, hide_index=True, height=500)
