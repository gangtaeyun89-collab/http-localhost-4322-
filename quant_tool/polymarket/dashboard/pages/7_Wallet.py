"""Live wallet view -- on-chain USDC balance + open Polymarket positions.

Reads from Polygon RPC + Polymarket's data-api. No private key is needed; all
calls are read-only. The wallet address comes from your ``.env``
(POLYMARKET_PROXY_ADDRESS) so the dashboard always reflects what's in the
proxy wallet on-chain, even when the bot isn't running.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import os
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quant_tool.polymarket import from_environ, load_dotenv
from quant_tool.polymarket.onchain.reader import WalletReader, WalletSnapshot


st.set_page_config(page_title="Wallet", layout="wide")
load_dotenv()
st.title("Wallet (live on-chain)")
st.caption("USDC.e balance + open Polymarket positions from the proxy wallet, "
            "read fresh every time you click **Refresh**.")

env = from_environ()
# Hardcoded fallback so the address is always pre-filled even before secrets load.
DEFAULT_PROXY_ADDRESS = "0xa8Fd04Ad1A2FF5a57D850A5bE6Fce5D28848C52f"
default_address = env.proxy_address or env.wallet_address or DEFAULT_PROXY_ADDRESS

# ---- address picker ----
address = st.text_input("Polymarket wallet address (proxy preferred)",
                         value=default_address,
                         help="The 0x... address that holds your USDC.e and conditional "
                              "tokens. Polymarket's proxy wallet -- not your MetaMask EOA -- "
                              "is what actually owns the positions.")
if not address:
    st.info("Set `POLYMARKET_PROXY_ADDRESS` in `.env` or paste an address above.")
    st.stop()

# ---- RPC + data-api endpoints (overrideable for debug) ----
with st.expander("Endpoints", expanded=False):
    rpc_url = st.text_input("Polygon RPC", value=env.polygon_rpc_url)
    data_api = st.text_input("Polymarket data API",
                              value=os.environ.get("POLYMARKET_DATA_API_URL",
                                                    "https://data-api.polymarket.com"))

reader = WalletReader(polygon_rpc_url=rpc_url, data_api_url=data_api)

# ---- session history of snapshots for the equity sparkline ----
HIST_KEY = "wallet_history"
if HIST_KEY not in st.session_state:
    st.session_state[HIST_KEY] = []  # list[WalletSnapshot]

c1, c2 = st.columns([1, 5])
refresh = c1.button("Refresh now", type="primary", use_container_width=True)
auto = c2.checkbox("Auto-refresh every 30s", value=False,
                    help="Re-runs this page every 30 seconds. Polygon RPC and the "
                         "Polymarket data-api are both free public endpoints, but "
                         "they rate-limit aggressively -- don't go below 10s.")

if refresh or not st.session_state[HIST_KEY]:
    with st.spinner("Reading on-chain state..."):
        snap = reader.snapshot(address)
    st.session_state[HIST_KEY].append(snap)
    # Cap history at 200 points so the sidebar doesn't bloat across long sessions.
    if len(st.session_state[HIST_KEY]) > 200:
        st.session_state[HIST_KEY] = st.session_state[HIST_KEY][-200:]
elif auto:
    import time
    time.sleep(30)
    st.rerun()

history: list[WalletSnapshot] = st.session_state[HIST_KEY]
snap = history[-1]

# ---- KPI strip ----
col1, col2, col3, col4 = st.columns(4)
col1.metric("USDC.e balance", f"${snap.usdc_balance:,.2f}")
col2.metric("Open positions value", f"${snap.total_position_value:,.2f}",
            help="Mark-to-market value of open conditional-token positions.")
col3.metric("Total equity", f"${snap.total_equity:,.2f}",
            delta=(f"${snap.total_equity - history[0].total_equity:+,.2f} this session"
                   if len(history) > 1 else None))
col4.metric("Unrealised PnL", f"${snap.unrealised_pnl_total:+,.2f}",
            help="Reported by Polymarket's data-api as the gap between avg entry and current mid.")

st.caption(f"Fetched {snap.fetched_at.isoformat()} from `{address}`")

st.divider()

# ---- Equity sparkline over the session ----
if len(history) >= 2:
    st.subheader("Equity over this session")
    df = pd.DataFrame([{"t": s.fetched_at, "equity": s.total_equity,
                          "usdc": s.usdc_balance, "positions": s.total_position_value}
                          for s in history])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["t"], y=df["equity"], name="Total equity",
                              line=dict(color="#1f77b4", width=2)))
    fig.add_trace(go.Scatter(x=df["t"], y=df["usdc"], name="USDC cash",
                              line=dict(color="#2ca02c", width=1)))
    fig.add_trace(go.Scatter(x=df["t"], y=df["positions"], name="Positions value",
                              line=dict(color="#ff7f0e", width=1)))
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10),
                       xaxis_title=None, yaxis_title="USDC",
                       legend=dict(orientation="h", y=1.05))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Refresh a second time to start the session equity curve.")

# ---- Position table ----
st.subheader(f"Open positions ({len(snap.positions)})")
if not snap.positions:
    st.info("No open positions in this wallet.")
else:
    rows = [{
        "Market": p.market_question[:70],
        "Outcome": p.outcome,
        "Shares": round(p.size, 2),
        "Avg entry": round(p.avg_price, 4),
        "Current": round(p.current_price, 4),
        "Value ($)": round(p.current_value, 2),
        "Unrealised PnL ($)": round(p.unrealised_pnl, 2),
    } for p in snap.positions]
    df = pd.DataFrame(rows).sort_values("Value ($)", ascending=False)
    st.dataframe(df, use_container_width=True, hide_index=True, height=400)

    # Allocation pie
    st.subheader("Allocation by market")
    alloc = df.assign(Label=df["Market"].str.slice(0, 40) + " (" + df["Outcome"] + ")")
    fig = go.Figure(data=[go.Pie(labels=alloc["Label"], values=alloc["Value ($)"], hole=0.4)])
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10),
                       showlegend=True, legend=dict(orientation="v"))
    st.plotly_chart(fig, use_container_width=True)
