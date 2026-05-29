#!/bin/bash
# Cron wrapper for daily crypto rebalance (A4).
# Cron provides minimal env — set what the scripts need.
export HOME=/Users/george
cd /Users/george/Desktop/Projects/FIRE
exec /Users/george/.local/bin/uv run python3 scripts/daily_crypto_rebalance.py \
  >> data/daily_rebalance_stdout.log 2>> data/daily_rebalance_stderr.log
