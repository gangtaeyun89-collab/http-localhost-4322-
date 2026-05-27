#!/usr/bin/env bash
# Refresh the CSV universe from IBKR.
#
# The FastAPI backend reads market_data/industries/*.csv directly; this
# script is the official refresh path. Run it daily after the US close
# (or on demand) -- the API doesn't fetch from IBKR itself, by design,
# because a fetch round-trip is far too slow for a polling endpoint.
#
# Usage
# -----
# Default (all 26 industry baskets, 2020-01-01 to today)::
#
#     ./scripts/refresh_data.sh
#
# Custom universe / start / output directory::
#
#     UNIVERSE=sp500_semiconductors OUT_DIR=market_data/semis \
#     START=2020-01-01 ./scripts/refresh_data.sh
#
# Schedule via cron (daily 06:00 ET = 11:00 UTC, weekdays)::
#
#     0 11 * * 1-5  /Users/you/AI\ Trading/scripts/refresh_data.sh \
#                   >> /Users/you/AI\ Trading/logs/refresh.log 2>&1
#
# Schedule via macOS launchd: see scripts/refresh_data.plist.example.
#
# Prerequisites: IB Gateway / TWS running locally on the configured port
# (7497 = Paper, 7496 = Live) with the API enabled.
set -euo pipefail
cd "$(dirname "$0")/.."

UNIVERSE="${UNIVERSE:-all_industries}"
OUT_DIR="${OUT_DIR:-market_data/industries}"
START="${START:-2020-01-01}"
TIMEFRAME="${TIMEFRAME:-1d}"
PORT="${IBKR_PORT:-7497}"
CLIENT_ID="${IBKR_CLIENT_ID:-31}"

if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

stamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
echo "[$(stamp)] refresh start universe=$UNIVERSE timeframe=$TIMEFRAME out=$OUT_DIR"

python download_ibkr.py \
  --universe "$UNIVERSE" \
  --timeframe "$TIMEFRAME" \
  --start "$START" \
  --out-dir "$OUT_DIR" \
  --port "$PORT" \
  --client-id "$CLIENT_ID"

# Tell the FastAPI process (if running) to drop its cached universe so
# the next /api/pairs/* hit picks up the new bars. We use SIGHUP as a
# soft "refresh" signal; uvicorn re-imports modules and the lru_cache
# on load_universe() resets along with the rest of the app.
if [ -n "${STATARB_BACKEND_PID_FILE:-}" ] && [ -f "$STATARB_BACKEND_PID_FILE" ]; then
  PID="$(cat "$STATARB_BACKEND_PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "[$(stamp)] HUP backend pid=$PID"
    kill -HUP "$PID" || true
  fi
fi

echo "[$(stamp)] refresh done"
