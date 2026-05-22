#!/bin/bash
set -euo pipefail
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then exit 0; fi
cd "${CLAUDE_PROJECT_DIR:-.}"
if [ -f requirements.txt ]; then
  echo "session-start hook: installing Python dependencies..."
  pip install --quiet -r requirements.txt && echo "session-start hook: dependencies ready."
else
  echo "session-start hook: no requirements.txt found."
fi
