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
