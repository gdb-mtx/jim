"""Scheduled A1/A2 rebalance — every 21 trading days on the live calendar,
unattended. Replaces the manual "preview → execute at 3 PM ET" click
(2026-09-09; the manual cycle slipped 8 days in August and A2 missed a
cycle outright).

Fired by cron HOURLY with `--if-due` (the daily_crypto_rebalance pattern):
each fire decides for itself whether a rebalance is due and exits silently
otherwise, which makes the schedule timezone-immune and sleep-tolerant.

Due, per account, when all of:
  1. The latest settled S&P bar is a re-ranking grid date — the bar before
     a live rebalance date — or was within the last CATCHUP_DAYS (a missed
     fire trades the same ranking a day or two late rather than 21 days
     late). Computed with the strategies' own `rebalance_dates` on the
     same cache, so "due" and "fresh ranking" can never disagree.
  2. No rebalance is journaled for the account after that grid date —
     manual, filter-monitor or scheduled all count.
  3. The market is open and closes within TRADE_WINDOW_MIN (the 15:10 ET
     hourly fire on normal days, 12:10 ET on early closes). `--force`
     skips this check.

Usage:
  uv run python3 scripts/scheduled_rebalance.py --if-due            # cron mode
  uv run python3 scripts/scheduled_rebalance.py --dry-run           # report due-ness, trade nothing
  uv run python3 scripts/scheduled_rebalance.py --force --account 1 # rebalance now, off-schedule
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.trading_dates import ET, REBALANCE_PERIOD_DAYS, today_et  # noqa: E402
from execution.alpaca_broker import ACCOUNT_INFO, AlpacaBroker, active_accounts  # noqa: E402
from execution.notifications import notify_macos  # noqa: E402
from execution.rebalance_runner import rebalance_account  # noqa: E402

LOG_FILE = PROJECT_ROOT / "data" / "scheduled_rebalance.log"
SOURCE = "scheduled_rebalance"
CATCHUP_DAYS = 7
TRADE_WINDOW_MIN = 75

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)],
)
logging.Formatter.converter = time.gmtime
log = logging.getLogger("fire.scheduled_rebalance")


def last_grid_date() -> pd.Timestamp:
    """Most recent re-ranking grid date on settled S&P bars (before today ET)."""
    from data.sp500 import download_sp500_prices
    from strategies.base import rebalance_dates

    idx = download_sp500_prices().index
    settled = idx[idx < pd.Timestamp(today_et())]
    return rebalance_dates(settled, REBALANCE_PERIOD_DAYS)[-1]


def last_rebalance_after(account: int, grid: pd.Timestamp) -> str | None:
    """Timestamp of the newest journal entry for `account` dated after the grid date, else None."""
    from execution.rebalance_log import get_recent_rebalances

    for r in get_recent_rebalances(limit=300):
        if r.get("account") != account:
            continue
        ts = pd.Timestamp(r["timestamp"]).tz_convert(ET)
        return r["timestamp"] if ts.date() > grid.date() else None
    return None


def is_due(account: int, grid: pd.Timestamp) -> tuple[bool, str]:
    age = (pd.Timestamp(today_et()) - grid).days
    if age > CATCHUP_DAYS:
        return False, f"last grid {grid.date()} is {age}d ago — outside catch-up window"
    done = last_rebalance_after(account, grid)
    if done:
        return False, f"already rebalanced {done[:16]} (after grid {grid.date()})"
    return True, f"grid {grid.date()} ranked {age}d ago and not yet traded"


def in_trade_window(broker: AlpacaBroker) -> tuple[bool, str]:
    clock = broker.api.get_clock()
    if not clock.is_open:
        return False, "market closed"
    mins = (pd.Timestamp(clock.next_close) - pd.Timestamp(clock.timestamp)).total_seconds() / 60
    if mins > TRADE_WINDOW_MIN:
        return False, f"{mins:.0f} min to close — waiting for the last-hour fire"
    return True, f"{mins:.0f} min to close"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--if-due", action="store_true", help="cron mode: exit silently unless due now")
    ap.add_argument("--dry-run", action="store_true", help="report due-ness, trade nothing")
    ap.add_argument("--force", action="store_true", help="rebalance now regardless of schedule/window")
    ap.add_argument("--account", type=int, action="append", help="restrict to account(s)")
    args = ap.parse_args()

    accounts = args.account or list(active_accounts())
    grid = last_grid_date()

    due = {}
    for acct in accounts:
        ok, why = (True, "forced") if args.force else is_due(acct, grid)
        due[acct] = ok
        log.info(f"Account {acct}: {'DUE' if ok else 'not due'} — {why}")
    todo = [a for a, ok in due.items() if ok]
    if not todo:
        return 0

    if not args.force:
        ok, why = in_trade_window(AlpacaBroker(account=todo[0]))
        log.info(f"Trade window: {why}")
        if not ok:
            return 0

    log.info(f"Scheduled rebalance starting: accounts {todo} (grid {grid.date()}, ET {datetime.now(ET):%H:%M})")
    results = [rebalance_account(a, source=SOURCE, dry_run=args.dry_run, log=log) for a in todo]

    parts = []
    for r in results:
        label = ACCOUNT_INFO[r["account"]]["label"]
        if r["status"] == "executed":
            parts.append(f"{label}: {r['orders']} orders" + (f" ({r['failed']} failed)" if r.get("failed") else ""))
        else:
            parts.append(f"{label}: {r['status'].upper()}" + (f" — {r.get('reason') or r.get('error') or ''}"[:80]))
    summary = "; ".join(parts)
    log.info(f"Scheduled rebalance done: {summary}")
    if not args.dry_run:
        bad = any(r["status"] not in ("executed", "no_trades") for r in results)
        notify_macos("Jim Scheduled Rebalance" + (" — ATTENTION" if bad else ""), summary[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
