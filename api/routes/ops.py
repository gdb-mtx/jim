"""Ops endpoints — automation surface for the Ops dashboard tab.

Four endpoints answer "is everything running and when did it last run?":

- `GET /api/ops/scheduler`  — APScheduler jobs + launchd filter monitors
- `GET /api/ops/filters`    — SPY/BTC filter state + plausibility
- `GET /api/ops/validation` — per-account validation status + expiry
- `GET /api/ops/events`     — unified timeline (rebalances + filter flips)

All handlers wrap blocking I/O in `asyncio.to_thread` per project rule
(CLAUDE.md "Async endpoints must use asyncio.to_thread for blocking calls").
`api.main` is imported lazily inside the scheduler handler to dodge the
circular import with `api/main.py` (which include_router's this module).
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VALIDATION_STATE_PATH = PROJECT_ROOT / "data" / "risk_state" / "validation_state.json"
VALIDATION_REPORTS_DIR = PROJECT_ROOT / "data" / "validation_reports"

# launchd plists currently registered. Source tags are set by the plists
# themselves (FIRE_FILTER_CHECK_SOURCE env var); see
# `scripts/com.fire.filter-check-{equity,crypto}.plist`. Order matters for
# stable UI rendering.
LAUNCHD_JOBS: list[tuple[str, str, str]] = [
    # (plist_label, source_tag, expected_scope)
    ("com.fire.filter-check-equity", "launchd-equity", "spy"),
    ("com.fire.filter-check-crypto", "launchd-crypto", "btc"),
]


def _relative_time(seconds: float) -> str:
    """Compact human-readable age ('42s ago', '12m ago', '3h ago', '5d ago')."""
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


@router.get("/scheduler")
async def get_scheduler():
    """APScheduler jobs + launchd filter-monitor last-run state."""
    from api import main as api_main
    from data import filter_check_log

    def _compute():
        # --- APScheduler block ---
        aps: dict = {"running": False, "jobs": []}
        scheduler = api_main.scheduler
        if scheduler is not None:
            aps["running"] = bool(getattr(scheduler, "running", False))
            try:
                jobs = scheduler.get_jobs()
            except Exception as e:
                aps["error"] = f"get_jobs failed: {e}"
                jobs = []
            for job in jobs:
                info = api_main._last_run_info.get(job.id, {}) or {}
                next_run = getattr(job, "next_run_time", None)
                aps["jobs"].append({
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": next_run.isoformat() if next_run else None,
                    "last_started": info.get("started"),
                    "last_finished": info.get("finished"),
                    "last_status": info.get("status"),
                    "error": info.get("error"),
                })

        # --- launchd block ---
        try:
            runs = filter_check_log.parse_filter_check_log()
        except Exception as e:
            runs = []
            launchd_error = f"log parse failed: {e}"
        else:
            launchd_error = None

        latest = filter_check_log.latest_per_source(runs)
        launchd: list[dict] = []
        for label, source_tag, expected_scope in LAUNCHD_JOBS:
            run = latest.get(source_tag)
            if run is None:
                launchd.append({
                    "label": label,
                    "source": source_tag,
                    "expected_scope": expected_scope,
                    "last_run": None,
                    "outcome": None,
                    "scope": None,
                    "flips": [],
                    "accounts": [],
                    "last_run_relative": None,
                })
            else:
                # Log timestamps are naive laptop-local. Localize to UTC
                # so `last_run` serializes with an explicit +00:00 offset,
                # matching the UTC convention used elsewhere (filter_state
                # `last_checked`, rebalance_log timestamps) and letting
                # downstream string comparisons sort correctly.
                utc_started = run.started_at.astimezone(timezone.utc)
                age_s = (datetime.now() - run.started_at).total_seconds()
                launchd.append({
                    "label": label,
                    "source": source_tag,
                    "expected_scope": expected_scope,
                    "last_run": utc_started.isoformat(),
                    "last_run_relative": _relative_time(age_s),
                    "outcome": run.outcome,
                    "scope": run.scope,
                    "flips": run.flips,
                    "accounts": run.accounts,
                    "is_dry_run": run.is_dry_run,
                })

        result: dict = {"apscheduler": aps, "launchd": launchd}
        if launchd_error:
            result["launchd_error"] = launchd_error
        return result

    return await asyncio.to_thread(_compute)


@router.get("/filters")
async def get_filters():
    """Filter state (SPY/BTC scalars, prices, MAs, last flips) + plausibility."""
    from data import filter_state

    def _compute():
        state = filter_state.load_with_plausibility()
        last_checked = state.get("last_checked")
        if last_checked:
            try:
                dt = datetime.fromisoformat(last_checked)
                age_s = (datetime.now(timezone.utc) - dt).total_seconds()
                state["last_checked_relative"] = _relative_time(age_s)
            except (ValueError, TypeError):
                state["last_checked_relative"] = None
        else:
            state["last_checked_relative"] = None
        return state

    return await asyncio.to_thread(_compute)


@router.get("/validation")
async def get_validation():
    """Per-account validation status + days_remaining + report path.

    Reads `data/risk_state/validation_state.json` and enriches each account
    entry with:
      - `account`: int extracted from the `account_N` key
      - `days_remaining`: `expires` - today_et(), or None if no expires
      - `report_path`: relative path to the latest markdown report for this
        account on `last_run` date, or None if no matching file exists
    """
    from data.trading_dates import today_et

    def _compute():
        if not VALIDATION_STATE_PATH.exists():
            return {"accounts": []}
        with open(VALIDATION_STATE_PATH) as f:
            raw = json.load(f)

        today = date.fromisoformat(today_et())
        accounts: list[dict] = []
        for key, entry in raw.items():
            if not key.startswith("account_"):
                continue
            try:
                acct_num = int(key.split("_", 1)[1])
            except (ValueError, IndexError):
                continue

            enriched = dict(entry)
            enriched["account"] = acct_num

            expires = entry.get("expires")
            days_remaining: int | None = None
            if expires:
                try:
                    exp_date = date.fromisoformat(expires)
                    days_remaining = (exp_date - today).days
                except ValueError:
                    days_remaining = None
            enriched["days_remaining"] = days_remaining

            # Derive report path by globbing for the last_run date.
            # Reports are named `account_{N}_{YYYYMMDD}_{HHMMSS}.md`.
            enriched["report_path"] = None
            last_run = entry.get("last_run")
            if last_run:
                try:
                    lr_date = date.fromisoformat(last_run)
                    pattern = f"account_{acct_num}_{lr_date.strftime('%Y%m%d')}_*.md"
                    matches = sorted(VALIDATION_REPORTS_DIR.glob(pattern))
                    if matches:
                        # Latest timestamp for that date.
                        enriched["report_path"] = str(matches[-1].relative_to(PROJECT_ROOT))
                except ValueError:
                    pass

            accounts.append(enriched)

        accounts.sort(key=lambda a: a["account"])
        return {"accounts": accounts}

    return await asyncio.to_thread(_compute)


@router.get("/events")
async def get_events(
    limit: int = Query(default=50, ge=1, le=500),
    since: Optional[str] = Query(default=None, description="ISO timestamp, inclusive"),
    source: Optional[str] = Query(default=None, description="Exact source tag match"),
    event_type: Optional[str] = Query(
        default=None, alias="type", description="rebalance | filter_flip"
    ),
):
    """Unified event timeline merging rebalance_log.jsonl + filter_check.log.

    - Rebalance events come from `data/rebalance_log.jsonl`
      (sources: `manual`, `scheduled`, `filter_monitor`, `halt_reset`).
    - Filter-flip events come from `data/filter_check.log` runs where the
      computed scalar crossed (outcome="flip").

    Sorted newest-first. On shared timestamps, `filter_flip` renders above
    the rebalance it triggered so causal order is preserved visually.
    """
    from data import filter_check_log
    from execution.rebalance_log import get_recent_rebalances

    def _compute():
        # Parse `since` once upfront. Defensive against non-str input so a
        # malformed query param can't crash the handler.
        since_utc: datetime | None = None
        since_naive: datetime | None = None
        if isinstance(since, str) and since:
            try:
                since_utc = datetime.fromisoformat(since)
                if since_utc.tzinfo is None:
                    since_naive = since_utc
                else:
                    # Log times are naive laptop-local; approximate by dropping tz.
                    since_naive = since_utc.replace(tzinfo=None)
            except ValueError:
                pass

        events: list[dict] = []

        # --- Rebalance events ---
        try:
            rebalances = get_recent_rebalances(limit=500)
        except Exception:
            rebalances = []
        for r in rebalances:
            ts = r.get("timestamp")
            if not ts:
                continue
            try:
                event_dt = datetime.fromisoformat(ts)
            except ValueError:
                continue
            if since_utc is not None and event_dt < since_utc:
                continue
            n_orders = r.get("orders_submitted", 0) or 0
            n_failed = r.get("orders_failed", 0) or 0
            src = r.get("source", "manual")
            if src == "halt_reset":
                summary = "Catastrophe halt cleared"
            else:
                parts = [f"{n_orders} orders submitted"]
                if n_failed:
                    parts.append(f"{n_failed} failed")
                if r.get("execute_error"):
                    parts.append(f"error: {r['execute_error']}")
                summary = ", ".join(parts)
            events.append({
                "timestamp": ts,
                "type": "rebalance",
                "source": src,
                "account": r.get("account"),
                "summary": summary,
                "is_dry_run": False,
                "details": r,
            })

        # --- Filter-flip events ---
        try:
            runs = filter_check_log.parse_filter_check_log()
        except Exception:
            runs = []
        for run in runs:
            if run.outcome != "flip":
                continue
            if since_naive is not None and run.started_at < since_naive:
                continue
            # Normalize naive log timestamp to UTC so it sorts correctly
            # against rebalance timestamps (which are already UTC-aware).
            # Without this, "15:30+00:00" string-compares greater than
            # "15:08" even though the latter is actually 6h later in real
            # time when the log tz is MDT (=UTC-6).
            utc_started = run.started_at.astimezone(timezone.utc)
            for flip in run.flips:
                summary = (
                    f"{flip['filter'].upper()} filter "
                    f"{flip['from']} → {flip['to']} ({flip['direction']})"
                )
                events.append({
                    "timestamp": utc_started.isoformat(),
                    "type": "filter_flip",
                    "source": run.source,
                    "account": None,
                    "summary": summary,
                    "is_dry_run": run.is_dry_run,
                    "details": {
                        "filter": flip["filter"],
                        "from": flip["from"],
                        "to": flip["to"],
                        "direction": flip["direction"],
                        "scope": run.scope,
                        "accounts_in_run": run.accounts,
                        "is_dry_run": run.is_dry_run,
                    },
                })

        # Optional post-filters.
        if source:
            events = [e for e in events if e["source"] == source]
        if event_type:
            events = [e for e in events if e["type"] == event_type]

        # Sort desc by timestamp. Tie-break: filter_flip above the rebalance
        # it triggered on shared timestamps (larger key wins under reverse).
        def _sort_key(e: dict) -> tuple:
            return (e["timestamp"], 1 if e["type"] == "filter_flip" else 0)

        events.sort(key=_sort_key, reverse=True)

        return {
            "events": events[:limit],
            "total": len(events),
        }

    return await asyncio.to_thread(_compute)
