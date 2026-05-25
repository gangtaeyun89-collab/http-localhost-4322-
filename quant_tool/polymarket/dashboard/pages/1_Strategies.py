import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

"""Per-strategy controls: enable/disable and edit parameters.

Changes are applied to ``st.session_state`` immediately. Re-run the backtest
from the **Overview** page sidebar to see the effect.
"""

from __future__ import annotations

import streamlit as st

from quant_tool.polymarket.dashboard.state import (
    ENABLED_KEY,
    PARAMS_KEY,
    init_defaults,
)
from quant_tool.polymarket.strategy import STRATEGY_REGISTRY


st.set_page_config(page_title="Strategies", layout="wide")
init_defaults()

st.title("Strategies")
st.caption("Enable / disable strategies and tune their parameters, then re-run the backtest.")

enabled = set(st.session_state[ENABLED_KEY])

# --- enable/disable ---
st.subheader("Enabled strategies")
cols = st.columns(len(STRATEGY_REGISTRY))
new_enabled: list[str] = []
for col, name in zip(cols, STRATEGY_REGISTRY):
    if col.checkbox(name, value=(name in enabled), key=f"enable_{name}"):
        new_enabled.append(name)
st.session_state[ENABLED_KEY] = tuple(new_enabled)

st.divider()

# --- parameter overrides ---
st.subheader("Parameters")
st.caption("Leave a field at its default to use the strategy's built-in value.")

params: dict[str, dict] = dict(st.session_state[PARAMS_KEY])

with st.expander("market_maker", expanded=("market_maker" in new_enabled)):
    p = params.get("market_maker", {})
    quote_size = st.number_input("quote_size (shares)", min_value=1.0,
                                  value=float(p.get("quote_size", 20.0)), step=1.0,
                                  key="mm_quote_size")
    min_spread_ticks = st.number_input("min_spread_ticks", min_value=1,
                                        value=int(p.get("min_spread_ticks", 2)), step=1,
                                        key="mm_min_spread_ticks")
    inventory_skew = st.number_input("inventory_skew (price per share)", min_value=0.0,
                                      value=float(p.get("inventory_skew", 0.001)),
                                      step=0.0005, format="%.4f",
                                      key="mm_inventory_skew")
    max_inv = st.number_input("max_inventory_shares", min_value=10.0,
                               value=float(p.get("max_inventory_shares", 200.0)), step=10.0,
                               key="mm_max_inv")
    params["market_maker"] = dict(quote_size=quote_size, min_spread_ticks=min_spread_ticks,
                                   inventory_skew=inventory_skew, max_inventory_shares=max_inv)

with st.expander("arb_yes_no", expanded=("arb_yes_no" in new_enabled)):
    p = params.get("arb_yes_no", {})
    min_edge = st.number_input("min_edge (price units)", min_value=0.0001,
                                value=float(p.get("min_edge", 0.005)),
                                step=0.001, format="%.4f",
                                key="arb_min_edge")
    max_clip = st.number_input("max_clip_shares", min_value=10.0,
                                value=float(p.get("max_clip_shares", 100.0)), step=10.0,
                                key="arb_max_clip")
    params["arb_yes_no"] = dict(min_edge=min_edge, max_clip_shares=max_clip)

with st.expander("signal_model", expanded=("signal_model" in new_enabled)):
    p = params.get("signal_model", {})
    ema_alpha = st.number_input("ema_alpha", min_value=0.01, max_value=1.0,
                                 value=float(p.get("ema_alpha", 0.2)), step=0.05,
                                 key="sig_alpha")
    momentum = st.number_input("momentum_threshold", min_value=0.0,
                                value=float(p.get("momentum_threshold", 0.01)),
                                step=0.005, format="%.4f",
                                key="sig_mom")
    take_size = st.number_input("take_size_shares", min_value=1.0,
                                 value=float(p.get("take_size_shares", 15.0)), step=1.0,
                                 key="sig_take")
    imb = st.number_input("book_imbalance_min (ask/bid ratio)", min_value=1.0,
                           value=float(p.get("book_imbalance_min", 1.5)),
                           step=0.1, key="sig_imb")
    params["signal_model"] = dict(ema_alpha=ema_alpha, momentum_threshold=momentum,
                                   take_size_shares=take_size, book_imbalance_min=imb)

with st.expander("copy_trader", expanded=False):
    st.write("Configured via wallet addresses, not a parameter sweep. "
             "Add followed wallets in `quant_tool/polymarket/strategy/copy_trader.py` "
             "or via the runner config.")

st.session_state[PARAMS_KEY] = params
st.info("Switch to **Overview** in the sidebar and click **Run backtest** to apply.")
