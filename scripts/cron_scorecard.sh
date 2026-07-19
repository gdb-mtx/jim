#!/bin/bash
# Weekly live scorecard — Monday 09:00 laptop-local. Report-only (no trades);
# a missed week is harmless. Deployed copy runs from ~/.fire-cron/ (TCC —
# see AUTOMATION.md); redeploy after edits: cp scripts/cron_scorecard.sh ~/.fire-cron/
export HOME="${HOME:-/Users/george}"
cd /Users/george/Desktop/Projects/FIRE || exit 1
/Users/george/.local/bin/uv run python3 scripts/live_scorecard.py --notify \
  >> data/scorecard_cron.log 2>&1
