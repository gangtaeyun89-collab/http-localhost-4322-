#!/usr/bin/env bash
# Start the FastAPI service from the repo root so quant_tool imports resolve.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uvicorn backend.app.main:app --reload --port 8000 "$@"
