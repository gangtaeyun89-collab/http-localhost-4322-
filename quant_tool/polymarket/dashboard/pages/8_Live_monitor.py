"""Live monitor -- watches the SQLite DB written by the live runner.

Reads run metadata, recent fills, equity curve, and current positions for the
selected run. Optional auto-refresh polls the DB every 5 seconds while the
runner is alive.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import time
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quant_tool.polymarket.storage import Storage, default_bot_log_path, default_db_path


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
cycle_metrics = storage.cycle_metrics_for_run(run.id)

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

# ----- Live activity (last cycle + per-cycle chart) -----
st.subheader("Bot activity")
if cycle_metrics:
    last_cycle = cycle_metrics[-1]
    age = (datetime.now(timezone.utc) - last_cycle.timestamp).total_seconds()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Last cycle", f"#{last_cycle.cycle_number}",
              delta=f"{age:.0f}s ago" if age < 600 else f"{age/60:.0f}min ago",
              delta_color="off")
    c2.metric("Markets observed", last_cycle.snapshots_seen,
              help=f"out of {last_cycle.universe_size} in the universe")
    c3.metric("Intents generated", last_cycle.intents_generated,
              delta=(f"-{last_cycle.intents_blocked} blocked"
                     if last_cycle.intents_blocked else None),
              delta_color="inverse" if last_cycle.intents_blocked else "off")
    c4.metric("Fills this cycle",
              last_cycle.fills_immediate + last_cycle.fills_rested)
    c5.metric("Cycle time", f"{last_cycle.elapsed_seconds:.1f}s",
              help="Wall-clock time to fetch universe + books + run strategies")

    # Per-cycle line chart -- shows the bot's activity rhythm even with no fills
    df = pd.DataFrame([{
        "cycle": m.cycle_number,
        "intents": m.intents_generated,
        "blocked": m.intents_blocked,
        "fills": m.fills_immediate + m.fills_rested,
        "markets": m.snapshots_seen,
    } for m in cycle_metrics])
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["cycle"], y=df["intents"], name="Intents",
                          marker_color="#1f77b4"))
    fig.add_trace(go.Bar(x=df["cycle"], y=df["blocked"], name="Blocked by risk",
                          marker_color="#ff7f0e"))
    fig.add_trace(go.Scatter(x=df["cycle"], y=df["fills"], name="Fills",
                              mode="lines+markers",
                              line=dict(color="#2ca02c", width=2),
                              marker=dict(size=8)))
    fig.update_layout(height=250, margin=dict(l=10, r=10, t=10, b=10),
                       barmode="overlay", xaxis_title="Cycle #",
                       yaxis_title="Count",
                       legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No cycle metrics yet -- the runner hasn't completed a cycle.")

# ----- Live log tail -----
st.subheader("Live bot log")
log_path = st.text_input("Bot log path", value=str(default_bot_log_path()),
                          help="The file the bot writes its activity to. On Fly.io "
                               "this is `/data/bot.log`; locally it's `data/bot.log`.")
log_p = Path(log_path)
if log_p.exists():
    try:
        lines = log_p.read_text(errors="replace").splitlines()[-40:]
        st.code("\n".join(lines) or "(empty)", language="text")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not read log: {exc}")
else:
    st.info(f"Log file not found at `{log_path}`. The bot writes here once it "
             "starts producing output.")

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
