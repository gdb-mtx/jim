"""ET trading-date helpers — TZ-stable across server timezones.

`date.today()` and naive `datetime.fromtimestamp(ts)` silently shift by a day on a
UTC server, so backfilled rows and live rows can disagree for the same session.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def today_et() -> str:
    """Current ET calendar date as 'YYYY-MM-DD'."""
    return datetime.now(ET).date().isoformat()


def utc_ts_to_et_date(ts: float) -> str:
    """Convert a Unix timestamp (seconds, UTC) to an ET calendar date 'YYYY-MM-DD'."""
    return datetime.fromtimestamp(ts, tz=UTC).astimezone(ET).date().isoformat()


# ---------------------------------------------------------------------------
# Live rebalance calendar
# ---------------------------------------------------------------------------

# A1/A2 rebalance every 21 trading days from this date. Every strategy's
# re-ranking grid is phased to it (strategies/base.py rebalance_dates), and
# scripts/scheduled_rebalance.py fires on these dates. HISTORY.md 2026-09-09.
REBALANCE_ANCHOR = "2026-04-21"
REBALANCE_PERIOD_DAYS = 21

# NYSE full-day closures. Extend each December; the scheduled rebalance only
# needs this for "next run" display — the due-check itself reads settled bars.
NYSE_HOLIDAYS = [
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
]


def live_rebalance_dates(end: str) -> list[str]:
    """Scheduled live rebalance dates from the anchor through `end` (ISO),
    on the NYSE calendar: the anchor and every 21 trading days after it."""
    import pandas as pd

    days = pd.bdate_range(REBALANCE_ANCHOR, end, freq="C", holidays=NYSE_HOLIDAYS)
    return [d.strftime("%Y-%m-%d") for d in days[::REBALANCE_PERIOD_DAYS]]


def next_live_rebalance_date(after: str) -> str:
    """First scheduled live rebalance date strictly after `after` (ISO)."""
    import pandas as pd

    horizon = (pd.Timestamp(after) + pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    return next(d for d in live_rebalance_dates(horizon) if d > after)
