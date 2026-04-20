"""ET trading-date helpers.

Snapshot dates must be stable across server timezones. AUDIT_MONTH2.md D1/D2:
`date.today()` and naive `datetime.fromtimestamp(ts)` silently shift by a day
if the server ever runs in UTC — backfilled (Alpaca UTC-midnight) rows and
live rows can then disagree for the same trading session.
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
