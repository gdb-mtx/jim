#!/bin/bash
# Cron wrapper for filter check (SPY/BTC).
# Usage: cron_filter_check.sh <spy|btc>
# Cron provides minimal env — set what the scripts need.
export HOME=/Users/george
cd /Users/george/Desktop/Projects/FIRE
exec /Users/george/.local/bin/uv run python3 scripts/filter_check.py --filter "$1" \
  >> data/filter_check_stdout.log 2>> data/filter_check_stderr.log
