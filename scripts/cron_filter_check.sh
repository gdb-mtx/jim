#!/bin/bash
# Cron wrapper for filter check (SPY/BTC).
# Usage: cron_filter_check.sh <spy|btc>
# DEPLOYED COPY runs from ~/.fire-cron/ (NOT from here): the project is under
# ~/Desktop (TCC-protected); a cron-launched script located there is denied
# getcwd ("Current directory does not exist") before Python starts, even with
# Full Disk Access on cron. Redeploy after editing:
#   cp scripts/cron_*.sh ~/.fire-cron/   (see AUTOMATION.md — diagnosed 2026-05-29)
# Cron provides minimal env — set what the scripts need.
export HOME=/Users/george
export FIRE_FILTER_CHECK_SOURCE="cron-$1"
cd /Users/george/Desktop/Projects/FIRE
exec /Users/george/.local/bin/uv run python3 scripts/filter_check.py --filter "$1" \
  >> data/filter_check_stdout.log 2>> data/filter_check_stderr.log
