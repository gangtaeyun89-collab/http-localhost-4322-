"""Polymarket bake-off ops console -- entry point.

Run from the repo root with:

    streamlit run quant_tool/polymarket/dashboard/app.py

Streamlit Cloud sets the working directory to the repo root but does *not*
add it to sys.path. We do that ourselves so ``from quant_tool...`` resolves
the same way it does locally.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from datetime import datetime, timezone

import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# When deployed on Streamlit Community Cloud, configuration values are stored
# in ``st.secrets`` rather than a ``.env`` file. Copy them into ``os.environ``
# so the same ``from_environ`` loader works in both environments.
try:
    for _k, _v in dict(st.secrets).items():  # type: ignore[union-attr]
        os.environ.setdefault(_k, str(_v))
except Exception:
    pass

from quant_tool.polymarket import load_dotenv
from quant_tool.polymarket.dashboard.state import (
    BACKTEST_KEY,
    CAPTURE_PATH_KEY,
    get_config,
    init_defaults,
    run_and_cache_backtest,
)
from quant_tool.polymarket.storage import default_capture_path


st.set_page_config(page_title="Polymarket Bot", page_icon=None, layout="wide")
load_dotenv()
init_defaults()

st.title("Polymarket bake-off")
st.caption("Local ops console -- read-only view of captured snapshots + paper-trade replays.")

# ---------- Sidebar: capture file + risk knobs ----------
# If the live bot has been writing a capture file, use that as the default so
# the Backtest button "just works" without anyone having to upload anything.
_live_capture = default_capture_path()
_default_path = str(st.session_state.get(CAPTURE_PATH_KEY)
                     or (_live_capture if _live_capture.exists() else ""))
with st.sidebar:
    st.header("Capture file")
    if _live_capture.exists() and not st.session_state.get(CAPTURE_PATH_KEY):
        st.success(f"Live bot capture detected: `{_live_capture}`")
    text_path = st.text_input("Path to JSONL capture",
                              value=_default_path,
                              help="Pre-filled with the live bot's capture if "
                                   "one exists. Override with a path, or upload below.")
    uploaded = st.file_uploader("...or upload one", type=["jsonl"])
    if uploaded is not None:
        target = Path(".dashboard_uploads")
        target.mkdir(exist_ok=True)
        dest = target / uploaded.name
        dest.write_bytes(uploaded.getbuffer())
        text_path = str(dest)

    # Quick on-demand capture so the user doesn't have to wait for the live
    # bot or upload anything. Three cycles of 10 markets takes ~15-30 seconds.
    if st.button("Generate capture now (3 cycles)", use_container_width=True):
        from datetime import datetime as _dt, timezone as _tz
        from quant_tool.polymarket.data.clob_client import ClobClient
        from quant_tool.polymarket.data.gamma_client import GammaClient
        from quant_tool.polymarket.data.snapshots import append_batch
        from quant_tool.polymarket.strategy.base import MarketSnapshot as _MS
        target = Path(".dashboard_uploads")
        target.mkdir(exist_ok=True)
        dest = target / f"inline_capture_{int(_dt.now().timestamp())}.jsonl"
        gamma = GammaClient()
        clob = ClobClient()
        progress = st.progress(0.0, text="Fetching universe...")
        try:
            universe = gamma.active_markets(limit=100)
            sample = universe[:10]
            for cycle in range(3):
                progress.progress((cycle + 0.1) / 3,
                                   text=f"Cycle {cycle+1}/3: fetching books...")
                snaps = []
                for m in sample:
                    try:
                        yb = clob.orderbook(m.yes_token().token_id)
                        nb = clob.orderbook(m.no_token().token_id)
                        snaps.append(_MS(market=m, yes_book=yb, no_book=nb))
                    except Exception:  # noqa: BLE001
                        pass
                if snaps:
                    append_batch(dest, snaps,
                                  captured_at=_dt.now(_tz.utc),
                                  universe_size=len(universe))
                progress.progress((cycle + 1) / 3,
                                   text=f"Cycle {cycle+1}/3 done.")
            progress.empty()
            text_path = str(dest)
            st.success(f"Captured 3 cycles to `{dest}`. Click **Run backtest**.")
        except Exception as exc:  # noqa: BLE001
            progress.empty()
            st.error(f"Capture failed: {exc}")
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

    max_batches = st.slider(
        "Max batches to replay",
        min_value=10, max_value=2000, value=200, step=10,
        help="Caps how many of the most recent batches the backtest replays. "
             "Smaller values run faster and avoid OOM on long captures.",
    )

    if st.button("Run backtest", type="primary", use_container_width=True):
        cfg = get_config()
        # Validate the inputs before we even start so the user gets a fast,
        # clear error instead of a hanging spinner.
        if cfg.capture_path is None or not Path(cfg.capture_path).exists():
            st.error("No capture file. Pick a path, upload one, or click "
                      "**Generate capture now** above.")
        else:
            progress = st.progress(0.0, text="Loading...")
            status = st.empty()
            try:
                def _on_progress(done: int, total: int) -> None:
                    pct = (done / total) if total else 0
                    progress.progress(min(1.0, pct),
                                       text=f"Replaying batch {done}/{total}")
                result = run_and_cache_backtest(
                    cfg, max_batches=int(max_batches),
                    progress_callback=_on_progress,
                )
            except Exception as exc:  # noqa: BLE001
                progress.empty()
                status.error(f"Backtest failed: {exc}")
                st.exception(exc)
                result = None
            else:
                progress.empty()
                if result is None:
                    status.error("Backtest returned no result.")
                else:
                    status.success(
                        f"Replayed {result.batches} batches "
                        f"({result.snapshots} snapshots, {result.prints_seen} prints).")

# ---------- Main panel ----------
result = st.session_state.get(BACKTEST_KEY)

if result is None:
    st.info("Upload a capture file in the sidebar and click **Run backtest** to begin.")
    st.markdown("""
    ### Quick start
    1. On your laptop, run:
       ```bash
       PYTHONPATH=. python scripts/polymarket_capture.py \\
           --output capture.jsonl --interval 60 --duration 3600 --markets 30
       ```
       Leave it running. It'll write to `capture.jsonl` in the current folder.
    2. **On this page**, click the **Upload** button in the sidebar and pick
       that `capture.jsonl` from your laptop. (The text path field only works
       if the file is on this server, which it isn't.)
    3. Click **Run backtest**.

    Then explore the **Strategies**, **Fills**, **Markets**, and **Backtest sweep** pages.

    ### Just want to see your wallet?
    Click **Wallet** in the sidebar -- no capture needed, it reads your
    USDC balance + positions directly from Polygon.
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
