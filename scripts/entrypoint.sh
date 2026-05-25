#!/usr/bin/env bash
# Runs the trading bot and the Streamlit dashboard in one container.
#
# The bot is backgrounded so it keeps producing fills while the dashboard
# serves HTTP. Both share the same SQLite database at $POLYMARKET_DB_PATH,
# which is on a persistent volume in production so state survives redeploys.

set -euo pipefail

mkdir -p "$(dirname "${POLYMARKET_DB_PATH:-/data/polymarket.sqlite}")"

# Start the bot in the background, redirecting its log to a file the
# dashboard's Bot control page tails.
mkdir -p /data
python scripts/polymarket_live.py \
    --db "${POLYMARKET_DB_PATH:-/data/polymarket.sqlite}" \
    --interval "${BOT_INTERVAL_SECONDS:-60}" \
    --markets "${BOT_MARKETS:-30}" \
    --bankroll "${BOT_BANKROLL:-10000}" \
    --max-per-market "${BOT_MAX_PER_MARKET:-0.02}" \
    --max-total "${BOT_MAX_TOTAL:-0.50}" \
    --strategies "${BOT_STRATEGIES:-market_maker,smart_market_maker,arb_yes_no,signal_model}" \
    --capture "${POLYMARKET_CAPTURE_PATH:-/data/capture.jsonl}" \
    --capture-every-n-cycles "${BOT_CAPTURE_EVERY_N:-1}" \
    > /data/bot.log 2>&1 &
BOT_PID=$!
echo "Bot started, PID=${BOT_PID}, logging to /data/bot.log"

# When the dashboard exits (or the container is signaled), kill the bot too.
trap 'echo "shutting down"; kill ${BOT_PID} 2>/dev/null || true; wait' SIGTERM SIGINT EXIT

# Serve the dashboard in the foreground -- Fly.io treats this process as the
# container's PID 1.
exec streamlit run quant_tool/polymarket/dashboard/app.py \
    --server.address 0.0.0.0 \
    --server.port "${PORT:-8080}" \
    --server.headless true \
    --browser.gatherUsageStats false
