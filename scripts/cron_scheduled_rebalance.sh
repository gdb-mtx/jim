#!/bin/bash
# Cron wrapper for the scheduled A1/A2 21-day rebalance.
# DEPLOYED COPY runs from ~/.fire-cron/ (NOT from here): the project is under
# ~/Desktop (TCC-protected); a cron-launched script located there is denied
# getcwd before Python starts, even with Full Disk Access on cron. Redeploy
# after editing:
#   cp scripts/cron_*.sh ~/.fire-cron/   (see AUTOMATION.md — diagnosed 2026-05-29)
# Cron provides minimal env — set what the scripts need.
export HOME=/Users/george
cd /Users/george/Desktop/Projects/FIRE
# --if-due: cron fires this every 10 MINUTES; the script decides whether a
# rebalance is due (settled bar = grid date, nothing journaled since, market
# open and inside the last 75 min before close) and exits silently otherwise.
# Timezone-immune and sleep-tolerant: six fires inside the window, so a
# closed lid at one fire minute no longer loses the day (2026-09-21).
exec /Users/george/.local/bin/uv run python3 scripts/scheduled_rebalance.py --if-due \
  >> data/scheduled_rebalance_stdout.log 2>> data/scheduled_rebalance_stderr.log
