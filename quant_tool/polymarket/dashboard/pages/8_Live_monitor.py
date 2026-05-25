import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

"""Live monitor -- watches the SQLite DB written by the live runner.

Reads run metadata, recent fills, equity curve, and current positions for the
selected run. Optional auto-refresh polls the DB every 5 seconds while the
runner is alive.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quant_tool.polymarket.storage import Storage, default_db_path


st.set_page_config(page_title="Live monitor", layout="wide")
st.title("Live monitor")
st.caption("Real-time view of the running paper-trade bot. Start it from a "
            "terminal with `python scripts/polymarket_live.py`.")

db_path = st.text_input("SQLite path", value=str(default_db_path()),
                         help="Defaults to data/polymarket.sqlite; override with "
                              "the POLYMARKET_DB_PATH env var.")

try:
    storage = Storage(db_path)
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not open database: {exc}")
    st.stop()

runs = storage.recent_runs(limit=20)
if not runs:
    st.info("No runs yet. Start one with:\n\n"
             "    PYTHONPATH=. python scripts/polymarket_live.py --db " + db_path)
    st.stop()

# Run picker -- default to the most recent
labels = []
for r in runs:
    status = "ALIVE" if r.is_alive else "ENDED" if r.ended_at else "STALE"
    labels.append(f"#{r.id} | {status} | {r.mode} | start {r.started_at.isoformat()} | "
                   f"{r.cycles_completed} cycles")
selected = st.selectbox("Run", range(len(runs)), format_func=lambda i: labels[i])
run = runs[selected]

# Auto-refresh
c1, c2 = st.columns([1, 5])
manual = c1.button("Refresh now", use_container_width=True)
auto = c2.checkbox("Auto-refresh every 5s while run is alive",
                    value=False, disabled=not run.is_alive)

# Load run data
fills = storage.fills_for_run(run.id, limit=500)
equity_rows = storage.equity_for_run(run.id)
positions = storage.positions_for_run(run.id, open_only=True)

# ----- KPI strip -----
status_color = "green" if run.is_alive else "orange" if not run.ended_at else "gray"
status_word = "ALIVE" if run.is_alive else "ENDED" if run.ended_at else "STALE"
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Status", status_word, help=f"PID {run.pid}; mode {run.mode}")
if equity_rows:
    last = equity_rows[-1]
    pnl = last.total_equity - run.bankroll
    c2.metric("Equity", f"${last.total_equity:,.2f}", delta=f"${pnl:+,.2f} vs start")
    c3.metric("Realised PnL", f"${last.realised_pnl:+,.2f}")
    c4.metric("Unrealised PnL", f"${last.unrealised_pnl:+,.2f}")
else:
    c2.metric("Equity", f"${run.bankroll:,.2f}")
    c3.metric("Realised PnL", "$0.00")
    c4.metric("Unrealised PnL", "$0.00")
c5.metric("Fills", len(fills),
           help=f"{len([f for f in fills if f.fill_type == 'rested'])} maker + "
                f"{len([f for f in fills if f.fill_type == 'immediate'])} taker")

if run.last_heartbeat_at:
    age = (datetime.now(timezone.utc) - run.last_heartbeat_at).total_seconds()
    st.caption(f"Last heartbeat **{age:.0f}s** ago "
                f"({run.last_heartbeat_at.isoformat()}); "
                f"{run.cycles_completed} cycles completed")

st.divider()

# ----- Equity curve -----
st.subheader("Equity curve")
if equity_rows:
    df = pd.DataFrame([{"t": r.timestamp, "equity": r.total_equity,
                          "cash": r.cash, "realised": r.realised_pnl,
                          "unrealised": r.unrealised_pnl}
                          for r in equity_rows])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["t"], y=df["equity"], name="Total equity",
                              line=dict(color="#1f77b4", width=2)))
    fig.add_trace(go.Scatter(x=df["t"], y=df["cash"], name="Cash",
                              line=dict(color="#2ca02c", width=1, dash="dot")))
    fig.add_hline(y=run.bankroll, line_dash="dash", line_color="gray",
                   annotation_text="Starting equity")
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                       yaxis_title="USDC", xaxis_title=None,
                       legend=dict(orientation="h", y=1.05))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No equity points yet -- the runner hasn't completed a cycle.")

# ----- Per-strategy attribution from fills -----
st.subheader("Per-strategy fills")
if fills:
    by_strat: dict[str, dict] = {}
    for f in fills:
        bucket = by_strat.setdefault(f.strategy,
                                       {"taker": 0, "maker": 0, "notional": 0.0})
        if f.fill_type == "immediate":
            bucket["taker"] += 1
        else:
            bucket["maker"] += 1
        bucket["notional"] += f.price * f.size
    df = pd.DataFrame([{"Strategy": k, **v} for k, v in by_strat.items()])
    df["Notional ($)"] = df["notional"].round(2)
    df["Total fills"] = df["taker"] + df["maker"]
    df = df[["Strategy", "Total fills", "taker", "maker", "Notional ($)"]]
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No fills yet.")

# ----- Recent fills -----
st.subheader(f"Recent fills (latest {min(50, len(fills))})")
if fills:
    df = pd.DataFrame([{
        "Time": f.timestamp.isoformat(),
        "Strategy": f.strategy,
        "Side": f.side,
        "Token": f.token_id[:14] + "...",
        "Price": f.price,
        "Size": f.size,
        "Notional ($)": round(f.price * f.size, 2),
        "Type": f.fill_type,
    } for f in fills[:50]])
    st.dataframe(df, use_container_width=True, hide_index=True, height=350)

# ----- Open positions -----
st.subheader(f"Open positions ({len(positions)})")
if positions:
    df = pd.DataFrame([{
        "Token": p.token_id[:14] + "...",
        "Condition": p.condition_id[:14] + "...",
        "Shares": round(p.shares, 2),
        "Avg price": round(p.avg_price, 4),
        "Realised PnL ($)": round(p.realised_pnl, 2),
    } for p in positions])
    st.dataframe(df, use_container_width=True, hide_index=True, height=300)

# Auto-refresh loop -- placed last so the page renders first, then sleeps + reruns.
if auto and run.is_alive:
    time.sleep(5)
    st.rerun()
