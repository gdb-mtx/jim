"""Scheduled A1/A2 rebalance — every 21 trading days on the live calendar,
unattended. Replaces the manual "preview → execute at 3 PM ET" click
(2026-09-09; the manual cycle slipped 8 days in August and A2 missed a
cycle outright).

Fired by cron every 10 minutes with `--if-due` (the daily_crypto_rebalance
pattern): each fire decides for itself whether a rebalance is due and exits
silently otherwise, which makes the schedule timezone-immune and
sleep-tolerant. Every 10 minutes, not hourly: on 2026-09-21 the single
15:10 ET fire fell inside a 13-minute closed-lid nap and the day was lost
(cron never catches up a missed minute). Six chances inside the window now.

Due, per account, when all of:
  1. Today is a live rebalance date on the NYSE calendar (every 21 sessions
     from REBALANCE_ANCHOR — data/trading_dates.live_rebalance_dates), or
     within CATCHUP_DAYS after one (a missed fire trades the same ranking
     a day or two late rather than 21 days late). Pure calendar: no price
     cache is read here. Until 2026-10-20 the due-check read the S&P cache
     through download_sp500_prices(), whose 24h TTL expired at ~15:31 every
     day — so the 10-minute cron re-downloaded pre-close, the unsettled-row
     guard dropped that day's bar, and the next rebalance day's grid bar
     was never in the cache ("not due" on 10-20; HISTORY.md).
  2. No rebalance is journaled for the account after that date's grid bar
     (the session before it) — manual, filter-monitor or scheduled all count.
  3. The market is open and closes within TRADE_WINDOW_MIN (15:00-16:00 ET
     on normal days, 12:00-13:00 ET on early closes). `--force` skips this
     check.

Before trading, the S&P cache must hold the grid bar (read directly, no
refresh path); if it doesn't, one forced refresh is attempted inside the
window. The runner then refuses to execute unless the ranking's as-of
date is exactly that grid bar (`require_signal_asof`), so a stale cache
can never put a month-old book on.

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

from data.trading_dates import ET, live_rebalance_dates, previous_session, today_et  # noqa: E402
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


def expected_rebalance(today: str) -> tuple[str, str] | None:
    """(live rebalance date, its grid bar) if a rebalance is scheduled for
    `today` or was within the last CATCHUP_DAYS; else None. Calendar only."""
    dates = live_rebalance_dates(today)
    if not dates:
        return None
    d = dates[-1]
    if (pd.Timestamp(today) - pd.Timestamp(d)).days > CATCHUP_DAYS:
        return None
    return d, previous_session(d)


def last_rebalance_after(account: int, grid: str) -> str | None:
    """Timestamp of the newest journal entry for `account` dated after the grid bar, else None."""
    from execution.rebalance_log import get_recent_rebalances

    for r in get_recent_rebalances(limit=300):
        if r.get("account") != account:
            continue
        ts = pd.Timestamp(r["timestamp"]).tz_convert(ET)
        return r["timestamp"] if ts.date() > pd.Timestamp(grid).date() else None
    return None


def is_due(account: int, today: str) -> tuple[bool, str]:
    exp = expected_rebalance(today)
    if exp is None:
        return False, "no rebalance date today or within the catch-up window"
    d, grid = exp
    done = last_rebalance_after(account, grid)
    if done:
        return False, f"already rebalanced {done[:16]} (after grid {grid})"
    late = (pd.Timestamp(today) - pd.Timestamp(d)).days
    return True, f"rebalance date {d}, grid {grid}" + (f" — {late}d late (catch-up)" if late else "")


def cache_has_bar(date: str) -> bool:
    """Does the S&P cache hold `date`? Direct parquet read — never the refresh path."""
    idx = pd.read_parquet(PROJECT_ROOT / "data" / "raw" / "sp500_prices.parquet").index
    return pd.Timestamp(date) in idx


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
    today = today_et()
    exp = expected_rebalance(today)
    grid = exp[1] if exp else previous_session(today)

    due = {}
    for acct in accounts:
        ok, why = (True, "forced") if args.force else is_due(acct, today)
        due[acct] = ok
        # cron mode fires 144x/day; only due-ness is worth a log line there
        (log.info if (ok or not args.if_due) else log.debug)(
            f"Account {acct}: {'DUE' if ok else 'not due'} — {why}")
    todo = [a for a, ok in due.items() if ok]
    if not todo:
        return 0

    if not args.force:
        ok, why = in_trade_window(AlpacaBroker(account=todo[0]))
        log.info(f"Trade window: {why}")
        if not ok:
            return 0

    # The ranking must come from the grid bar. Refresh once if it's missing
    # (slow — 5-45 min of yfinance — but inside the window beats a stale book).
    if not args.dry_run and not cache_has_bar(grid):
        log.warning(f"S&P cache lacks the grid bar {grid} — forcing a refresh inside the window")
        from data.sp500 import download_sp500_prices
        download_sp500_prices(force_refresh=True)
        if not cache_has_bar(grid):
            log.error(f"S&P cache still lacks {grid} after refresh — not trading")
            notify_macos("Jim Scheduled Rebalance — ATTENTION", f"grid bar {grid} missing from S&P cache after refresh; no trade")
            return 1

    log.info(f"Scheduled rebalance starting: accounts {todo} (grid {grid}, ET {datetime.now(ET):%H:%M})")
    results = [rebalance_account(a, source=SOURCE, dry_run=args.dry_run, log=log,
                                 require_signal_asof=None if args.force else grid) for a in todo]

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
