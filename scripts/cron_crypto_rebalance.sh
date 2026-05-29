#!/bin/bash
# Cron wrapper for daily crypto rebalance (A4).
# DEPLOYED COPY runs from ~/.fire-cron/ (NOT from here): the project is under
# ~/Desktop (TCC-protected); a cron-launched script located there is denied
# getcwd ("Current directory does not exist") before Python starts, even with
# Full Disk Access on cron. Redeploy after editing:
#   cp scripts/cron_*.sh ~/.fire-cron/   (see AUTOMATION.md — diagnosed 2026-05-29)
# Cron provides minimal env — set what the scripts need.
export HOME=/Users/george
cd /Users/george/Desktop/Projects/FIRE
exec /Users/george/.local/bin/uv run python3 scripts/daily_crypto_rebalance.py \
  >> data/daily_rebalance_stdout.log 2>> data/daily_rebalance_stderr.log
