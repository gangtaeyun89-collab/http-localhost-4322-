"""Streamlit ops console for the Polymarket bot.

Run with:
    streamlit run quant_tool/polymarket/dashboard/app.py

All pages share state via ``st.session_state``. Persistent state (selected
capture file, current backtest result) lives in the home page and is read by
the others, so navigating between pages doesn't reset your work.
"""
