"""Paper-trade manual order entry.

Lets you submit a single intent against any market+book from the loaded capture
and see the simulated fill. Useful for sanity-checking specific scenarios
without writing a strategy.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import streamlit as st

from quant_tool.polymarket.dashboard.state import (
    CAPTURE_PATH_KEY,
    init_defaults,
)
from quant_tool.polymarket.data.snapshots import iter_batches
from quant_tool.polymarket.execution.paper_broker import PaperBroker
from quant_tool.polymarket.strategy.base import Intent, Side


st.set_page_config(page_title="Manual order", layout="wide")
init_defaults()
st.title("Manual order entry (paper)")
st.caption("Build an intent, pick a market+side, see the simulated fill against "
            "the latest captured book. The live ClobBroker will reuse the same "
            "Intent type once we go live in July.")

cap = st.session_state.get(CAPTURE_PATH_KEY)
if not cap:
    st.info("Set a capture file on the **Overview** page first.")
    st.stop()

batches = list(iter_batches(cap))
if not batches:
    st.error("Capture is empty.")
    st.stop()

# Use the most recent batch as the order book.
batch = batches[-1]
st.caption(f"Using book from cycle at **{batch.captured_at.isoformat()}** "
            f"({len(batch.snapshots)} markets)")

market_idx = st.selectbox("Market", range(len(batch.snapshots)),
                           format_func=lambda i: batch.snapshots[i].market.question[:80])
snap = batch.snapshots[market_idx]
yes_tok = snap.market.yes_token()
no_tok = snap.market.no_token()

c1, c2, c3 = st.columns(3)
outcome = c1.radio("Outcome", ["YES", "NO"], horizontal=True)
side_str = c2.radio("Side", ["BUY", "SELL"], horizontal=True)
post_only = c3.radio("Order type", ["Post-only (maker)", "Crossing (taker)"], horizontal=True)

book = snap.yes_book if outcome == "YES" else snap.no_book
token = yes_tok if outcome == "YES" else no_tok

bb = book.best_bid()
ba = book.best_ask()
st.write(f"Current best: **bid {bb.price:.3f} ({bb.size:.0f})** "
         f"/ **ask {ba.price:.3f} ({ba.size:.0f})**" if bb and ba else "Book empty.")

if not (bb and ba):
    st.stop()

default_price = (bb.price if side_str == "BUY" else ba.price)
price = st.number_input("Price", min_value=0.01, max_value=0.99,
                         value=float(default_price), step=0.01, format="%.3f")
size = st.number_input("Size (shares)", min_value=1.0, value=20.0, step=1.0)

intent = Intent(
    strategy="manual",
    token_id=token.token_id,
    side=Side[side_str],
    price=price,
    size=size,
    post_only=(post_only.startswith("Post-only")),
)

if st.button("Simulate fill", type="primary"):
    broker = PaperBroker(starting_cash=10_000)
    fill = broker.submit(intent, book)
    if fill is None:
        if intent.post_only:
            st.info(f"Resting -- post-only at {price:.3f} would not cross the "
                     f"opposite side at {ba.price if side_str == 'BUY' else bb.price:.3f}.")
        else:
            st.warning("Taker did not cross -- price is outside the spread.")
    else:
        st.success(f"Filled **{fill.size:.0f}** shares at **{fill.price:.3f}** "
                    f"(notional ${fill.price * fill.size:.2f})")
        st.caption(f"Cash impact: ${-fill.price * fill.size if fill.side is Side.BUY else fill.price * fill.size:+,.2f}")
