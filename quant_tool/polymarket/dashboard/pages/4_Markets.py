"""Markets viewer -- inspect the orderbook of any market in the capture."""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quant_tool.polymarket.dashboard.state import CAPTURE_PATH_KEY
from quant_tool.polymarket.data.snapshots import iter_batches


st.set_page_config(page_title="Markets", layout="wide")


def _book_dataframe(book):
    rows = []
    for lvl in list(book.asks[:10])[::-1]:  # show worst ask at top, best at bottom
        rows.append({"Side": "ASK", "Price": lvl.price, "Size": lvl.size})
    for lvl in book.bids[:10]:
        rows.append({"Side": "BID", "Price": lvl.price, "Size": lvl.size})
    return pd.DataFrame(rows)


st.title("Markets")
st.caption("Browse the YES/NO orderbooks from any cycle in the capture.")

cap = st.session_state.get(CAPTURE_PATH_KEY)
if not cap:
    st.info("Set a capture file on the **Overview** page first.")
    st.stop()

batches = list(iter_batches(cap))
if not batches:
    st.error("Capture is empty.")
    st.stop()

# Cycle selector
batch_labels = [f"{i+1}: {b.captured_at.isoformat()}  ({len(b.snapshots)} markets)"
                 for i, b in enumerate(batches)]
selected_idx = st.selectbox("Batch", range(len(batches)),
                             format_func=lambda i: batch_labels[i],
                             index=len(batches) - 1)
batch = batches[selected_idx]

# Market selector within the batch
market_labels = [s.market.question[:80] for s in batch.snapshots]
mkt_idx = st.selectbox("Market", range(len(batch.snapshots)),
                        format_func=lambda i: market_labels[i])
snap = batch.snapshots[mkt_idx]

# Summary line
yb = snap.yes_book.best_bid()
ya = snap.yes_book.best_ask()
nb = snap.no_book.best_bid()
na = snap.no_book.best_ask()

c1, c2, c3, c4 = st.columns(4)
c1.metric("YES bid/ask", f"{yb.price:.3f} / {ya.price:.3f}" if yb and ya else "—",
           delta=f"{(ya.price - yb.price)*100:.1f}c spread" if yb and ya else None)
c2.metric("NO bid/ask", f"{nb.price:.3f} / {na.price:.3f}" if nb and na else "—",
           delta=f"{(na.price - nb.price)*100:.1f}c spread" if nb and na else None)
c3.metric("YES_bid + NO_bid",
           f"{yb.price + nb.price:.4f}" if yb and nb else "—",
           delta=f"{(yb.price + nb.price - 1.0)*100:+.2f}c vs 1.0" if yb and nb else None,
           help=">+0.5c = sell-both arb opportunity")
c4.metric("YES_ask + NO_ask",
           f"{ya.price + na.price:.4f}" if ya and na else "—",
           delta=f"{(ya.price + na.price - 1.0)*100:+.2f}c vs 1.0" if ya and na else None,
           help="<-0.5c = buy-both arb opportunity")

st.divider()

# Side-by-side orderbook
yc, nc = st.columns(2)
with yc:
    st.subheader("YES book")
    yes_df = _book_dataframe(snap.yes_book)
    st.dataframe(yes_df, use_container_width=True, hide_index=True, height=400)
with nc:
    st.subheader("NO book")
    no_df = _book_dataframe(snap.no_book)
    st.dataframe(no_df, use_container_width=True, hide_index=True, height=400)

# Recent prints
if snap.trades:
    st.subheader(f"Recent trade prints ({len(snap.trades)})")
    yes_id = snap.market.yes_token().token_id
    trades_df = pd.DataFrame([{
        "Time": t.timestamp.isoformat(),
        "Side": t.side,
        "Token": "YES" if t.token_id == yes_id else "NO",
        "Price": t.price,
        "Size": t.size,
    } for t in snap.trades])
    st.dataframe(trades_df, use_container_width=True, hide_index=True, height=250)
else:
    st.caption("No trade tape captured for this snapshot.")
