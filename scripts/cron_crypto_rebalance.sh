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
# --if-due: cron fires this HOURLY (at :10); the script itself decides whether
# today's UTC-date run has happened yet and exits silently otherwise. This is
# what makes the schedule timezone-immune and sleep-tolerant (2026-06-09 fix —
# the old once-daily `5 20 * * *` entry drifted off 00:05 UTC on travel and
# skipped entirely when the laptop slept through the fire minute).
exec /Users/george/.local/bin/uv run python3 scripts/daily_crypto_rebalance.py --if-due \
  >> data/daily_rebalance_stdout.log 2>> data/daily_rebalance_stderr.log
