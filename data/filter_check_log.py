"""Parser for `data/filter_check.log` written by `scripts/filter_check.py`.

The log is append-only and has no rotation policy. Readers must tail-scan
(bounded by `tail_bytes`) so the Ops endpoint's cost doesn't grow unbounded
as the file ages.

Each filter_check.py invocation emits a block starting with a 60-equals
separator and a `Jim Filter Check starting (source=X, scope=Y)` header
(`FIRE ...` before the 2026-08-12 rename; both parse).
Subsequent lines within the block include:

- `Filters computed in T.Ts: SPY=S.S (...) [, BTC=S.S (...)]`
- one of:
    - `No filter changes detected`
    - `First run — seeding filter state, no rebalance triggered`
    - `SPY filter changed: OLD → NEW (DIRECTION)`
    - `BTC filter changed: OLD → NEW (DIRECTION)`
- optional `Filter check complete: ...` followed by per-account summary
  lines of the form `  Account N: STATUS (N orders)`.

Older log entries (pre-2026-04-22 split into source/scope) lack the
`(source=..., scope=...)` suffix on the header — the parser tolerates
both forms.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("fire.filter_check_log")

DEFAULT_LOG_PATH = Path(__file__).resolve().parents[1] / "data" / "filter_check.log"

# 60-equals separator that fronts every filter_check.py invocation.
_SEPARATOR = "=" * 60

# Strict line prefix: `YYYY-MM-DD HH:MM:SS,mmm [LEVEL] `
_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \[(?P<level>\w+)\] (?P<msg>.*)$"
)
_HEADER_RE = re.compile(
    r"^(?:FIRE|Jim) Filter Check starting(?: \(source=(?P<source>[^,]+), scope=(?P<scope>[^)]+)\))?$"
)
_FLIP_RE = re.compile(
    r"^(?P<filter>SPY|BTC) filter changed: (?P<from>[\d.]+) → (?P<to>[\d.]+) \((?P<direction>\w+)\)$"
)
_SUMMARY_ACCOUNT_RE = re.compile(
    r"^  Account (?P<account>\d+): (?P<status>\w+) \((?P<orders>\d+) orders\)$"
)


@dataclass
class FilterCheckRun:
    """One filter_check.py invocation parsed from the log."""
    started_at: datetime
    source: str  # "launchd-equity" | "launchd-crypto" | "manual" | "unknown"
    scope: str   # "all" | "spy" | "btc" | "unknown"
    outcome: str  # "no_change" | "flip" | "first_run" | "error"
    flips: list[dict] = field(default_factory=list)
    # [{"filter": "btc", "from": 0.0, "to": 1.0, "direction": "BULLISH"}]
    accounts: list[dict] = field(default_factory=list)
    # [{"account": 4, "status": "executed", "orders": 2}]
    is_dry_run: bool = False
    # True for any non-production status (dry_run, blocked_by_harness); flips don't persist to filter_state.


def _read_tail(path: Path, tail_bytes: int) -> str:
    """Return the last `tail_bytes` of the file decoded as UTF-8.

    Reads from the end so parse cost stays bounded as the log grows. If the
    file is smaller than `tail_bytes`, returns the whole file.
    """
    if not path.exists():
        return ""
    size = path.stat().st_size
    with open(path, "rb") as f:
        if size > tail_bytes:
            f.seek(-tail_bytes, 2)
            # Discard the first partial line after seeking mid-file.
            f.readline()
        data = f.read()
    return data.decode("utf-8", errors="replace")


def _parse_timestamp(ts: str) -> datetime:
    # filter_check.py always logs in UTC (Formatter.converter = time.gmtime).
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f").replace(tzinfo=timezone.utc)


def _parse_block(lines: list[str]) -> Optional[FilterCheckRun]:
    """Parse one block of log lines into a FilterCheckRun.

    Returns None for blocks that lack a `Jim/FIRE Filter Check starting` header
    (stray log output, truncated separator-only blocks).
    """
    started_at: datetime | None = None
    source = "unknown"
    scope = "unknown"
    flips: list[dict] = []
    accounts: list[dict] = []
    outcome: str | None = None
    in_summary = False

    for raw in lines:
        m = _LINE_RE.match(raw)
        if not m:
            continue
        ts = m.group("ts")
        msg = m.group("msg")

        if started_at is None:
            hdr = _HEADER_RE.match(msg)
            if hdr:
                try:
                    started_at = _parse_timestamp(ts)
                except ValueError:
                    return None
                if hdr.group("source"):
                    source = hdr.group("source")
                if hdr.group("scope"):
                    scope = hdr.group("scope")
                continue
            # Skip lines before header (stray output).
            continue

        if msg == "No filter changes detected":
            outcome = "no_change"
            continue
        if msg.startswith("First run"):
            outcome = "first_run"
            continue

        flip = _FLIP_RE.match(msg)
        if flip:
            outcome = "flip"
            flips.append({
                "filter": flip.group("filter").lower(),
                "from": float(flip.group("from")),
                "to": float(flip.group("to")),
                "direction": flip.group("direction"),
            })
            continue

        if msg.startswith("Filter check complete:"):
            in_summary = True
            continue

        if in_summary:
            acct = _SUMMARY_ACCOUNT_RE.match(raw[raw.find("[INFO] ") + 7:]) if "[INFO] " in raw else None
            # Fall back to matching msg directly — the summary lines have
            # the `  Account N:` prefix embedded in `msg` after the `[INFO]`.
            if not acct:
                # msg starts with two spaces for these lines
                if msg.startswith("  Account "):
                    acct = _SUMMARY_ACCOUNT_RE.match(msg)
            if acct:
                accounts.append({
                    "account": int(acct.group("account")),
                    "status": acct.group("status"),
                    "orders": int(acct.group("orders")),
                })

    if started_at is None:
        return None

    is_dry_run = any(
        a.get("status") in ("dry_run", "blocked_by_harness")
        for a in accounts
    )

    return FilterCheckRun(
        started_at=started_at,
        source=source,
        scope=scope,
        outcome=outcome or "error",
        flips=flips,
        accounts=accounts,
        is_dry_run=is_dry_run,
    )


def parse_filter_check_log(
    path: Path | str = DEFAULT_LOG_PATH,
    tail_bytes: int = 200_000,
) -> list[FilterCheckRun]:
    """Parse the tail of filter_check.log into structured runs.

    Args:
        path: Log file path. Defaults to the project-root log.
        tail_bytes: Cap on bytes read from the end of the file. 200KB covers
            roughly the last 1000 filter_check runs at the current emission
            rate — plenty for a dashboard view.

    Returns:
        Runs in the order they appear in the log (chronological). Empty
        list on missing file or unparseable content.
    """
    path = Path(path)
    try:
        text = _read_tail(path, tail_bytes)
    except OSError as e:
        log.warning(f"filter_check.log unreadable: {e}")
        return []
    if not text:
        return []

    # Split on the separator line. Each block is one run.
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        # The separator line shows up as `[ts] [INFO] ==...==`.
        if line.endswith(_SEPARATOR):
            if current:
                blocks.append(current)
            current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)

    runs: list[FilterCheckRun] = []
    for block in blocks:
        try:
            run = _parse_block(block)
        except Exception as e:
            log.debug(f"skipping unparseable block: {e}")
            continue
        if run is not None:
            runs.append(run)
    return runs


def latest_per_source(runs: list[FilterCheckRun]) -> dict[str, FilterCheckRun]:
    """Return a dict mapping source tag → most recent run with that tag.

    Used to populate one Scheduler Panel row per launchd plist. Tags
    include `launchd-equity`, `launchd-crypto`, `manual`. Sources absent
    from the log are absent from the result — callers decide how to render
    "never fired" vs "not registered".
    """
    latest: dict[str, FilterCheckRun] = {}
    for run in runs:
        prev = latest.get(run.source)
        if prev is None or run.started_at > prev.started_at:
            latest[run.source] = run
    return latest
