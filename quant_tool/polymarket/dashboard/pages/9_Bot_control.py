"""Bot control -- start, stop, and watch the live paper-trade bot.

Start/Stop work when you're running this dashboard locally (it spawns the
``scripts/polymarket_live.py`` daemon as a subprocess on this machine).
On Streamlit Community Cloud the buttons are disabled and the page shows
instructions for running the bot somewhere with a persistent runtime --
typically your laptop, or a small VPS.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import os
import signal
import subprocess
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from quant_tool.polymarket.storage import Storage, default_bot_log_path, default_db_path
from quant_tool.polymarket.strategy import STRATEGY_REGISTRY


# ---------- environment detection ----------------------------------------

def on_streamlit_cloud() -> bool:
    """Best-effort heuristic. Streamlit Cloud mounts the repo at /mount/src."""
    if Path("/mount/src").exists():
        return True
    if os.environ.get("STREAMLIT_COMMUNITY_CLOUD"):
        return True
    return False


# ---------- bot lifecycle (only meaningful locally) ----------------------

PID_FILE = Path("data") / "bot.pid"
LOG_FILE = default_bot_log_path()


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def get_running_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        return None
    if _is_alive(pid):
        return pid
    # Stale file -- clean it up.
    PID_FILE.unlink(missing_ok=True)
    return None


def start_bot(*, db: str, bankroll: float, interval: float, markets: int,
              max_per_market: float, max_total: float, strategies: list[str]) -> int:
    """Spawn ``polymarket_live.py`` as a detached background process."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[4]
    cmd = [
        sys.executable, str(repo_root / "scripts" / "polymarket_live.py"),
        "--db", db,
        "--bankroll", str(bankroll),
        "--interval", str(interval),
        "--markets", str(markets),
        "--max-per-market", str(max_per_market),
        "--max-total", str(max_total),
        "--strategies", ",".join(strategies),
    ]
    env = {**os.environ, "PYTHONPATH": str(repo_root)}
    log = LOG_FILE.open("a")
    proc = subprocess.Popen(
        cmd, stdout=log, stderr=subprocess.STDOUT,
        cwd=repo_root, env=env, start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))
    return proc.pid


def stop_bot(pid: int) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    PID_FILE.unlink(missing_ok=True)
    return True


# ---------- UI -----------------------------------------------------------

st.set_page_config(page_title="Bot control", layout="wide")
st.title("Bot control")
st.caption("Start, stop, and watch the auto-trading bot.")

cloud = on_streamlit_cloud()
if cloud:
    st.warning(
        "**You're viewing this page on Streamlit Cloud.** "
        "The bot can't run here -- this host has no persistent background "
        "process. To actually trade, run the dashboard locally on your "
        "laptop (or a VPS) and open this page there. Then the **Start** "
        "button below will spawn the bot on that machine."
    )
    with st.expander("How to run the dashboard locally", expanded=False):
        st.code(
            "cd ~/polymarket-bot\n"
            "git pull origin claude/quirky-lamport-M8RDU\n"
            "source .venv/bin/activate\n"
            "pip install -r requirements.txt\n"
            "PYTHONPATH=. streamlit run quant_tool/polymarket/dashboard/app.py",
            language="bash",
        )
    st.divider()

# Configuration form
st.subheader("Configuration")
storage_path = st.text_input("SQLite database path",
                              value=str(default_db_path()),
                              help="Where the bot will write fills and equity.")
c1, c2, c3 = st.columns(3)
bankroll = c1.number_input("Bankroll (USDC)", min_value=100.0, value=10_000.0, step=100.0)
interval = c2.number_input("Cycle interval (seconds)", min_value=10.0, value=60.0, step=10.0)
markets = c3.number_input("Markets per cycle", min_value=1, value=30, step=5)

c4, c5 = st.columns(2)
max_per_market = c4.slider("Max position per market", min_value=0.005, max_value=0.20,
                            value=0.02, step=0.005, format="%.3f")
max_total = c5.slider("Max total exposure",      min_value=0.05,  max_value=1.0,
                       value=0.50, step=0.05,  format="%.2f")

strategies = st.multiselect(
    "Strategies",
    options=list(STRATEGY_REGISTRY),
    default=list(STRATEGY_REGISTRY),
)

st.divider()

# Current status
running_pid = get_running_pid()
status_cols = st.columns(4)

# Read DB state for the most recent run
try:
    storage = Storage(storage_path)
    latest_runs = storage.recent_runs(limit=1)
    last_run = latest_runs[0] if latest_runs else None
except Exception as exc:  # noqa: BLE001
    storage = None
    last_run = None
    st.error(f"Could not open database at `{storage_path}`: {exc}")

status_cols[0].metric("Process", "RUNNING" if running_pid else "STOPPED",
                       help=f"PID {running_pid}" if running_pid else "No bot.pid file")
if last_run:
    status_cols[1].metric("Last run", f"#{last_run.id}")
    status_cols[2].metric("Cycles", last_run.cycles_completed)
    status_cols[3].metric("Mode", last_run.mode)
else:
    status_cols[1].metric("Last run", "—")

# Start / Stop
st.divider()
st.subheader("Controls")
b1, b2, _ = st.columns([1, 1, 5])

start_disabled = cloud or running_pid is not None or not strategies
if b1.button("▶ Start bot", type="primary", disabled=start_disabled,
              use_container_width=True):
    try:
        pid = start_bot(
            db=storage_path, bankroll=bankroll, interval=interval,
            markets=int(markets), max_per_market=max_per_market,
            max_total=max_total, strategies=strategies,
        )
        st.success(f"Started bot (PID {pid}). Open **Live monitor** to watch it work.")
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to start: {exc}")

if b2.button("⏹ Stop bot", disabled=(running_pid is None or cloud),
              use_container_width=True):
    stop_bot(running_pid)  # type: ignore[arg-type]
    st.success("Stop signal sent. Process should exit within a cycle.")
    st.rerun()

if start_disabled and not cloud and not strategies:
    st.warning("Pick at least one strategy before starting.")
elif running_pid is not None and not cloud:
    st.info(f"Bot is already running (PID {running_pid}). Stop it before starting again.")

# Recent log tail (local only)
if not cloud and LOG_FILE.exists():
    st.divider()
    st.subheader("Recent bot log (last ~50 lines)")
    try:
        lines = LOG_FILE.read_text().splitlines()[-50:]
        st.code("\n".join(lines) or "(empty)", language="text")
    except Exception:  # noqa: BLE001
        pass
