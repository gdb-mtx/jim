"""Ops endpoints — automation surface for the Ops dashboard tab.

Four endpoints answer "is everything running and when did it last run?":

- `GET /api/ops/scheduler`  — launchd-fired daily rebalance + filter monitors
- `GET /api/ops/filters`    — SPY/BTC filter state + plausibility
- `GET /api/ops/validation` — per-account validation status + expiry
- `GET /api/ops/events`     — unified timeline (rebalances + filter flips)

All handlers wrap blocking I/O in `asyncio.to_thread` per project rule
(CLAUDE.md "Async endpoints must use asyncio.to_thread for blocking calls").

The scheduler endpoint reports two launchd-driven groups:
  - `scheduled_rebalance` — daily crypto rebalance (Account 4), last-run
    derived from `rebalance_log.jsonl` filtered by `source="scheduled"`.
    Replaces the old in-process APScheduler block (retired 2026-05-05).
  - `launchd` — filter monitors (SPY + BTC), last-run derived from
    `filter_check.log`.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter()

ALL_FIRE_LABELS = [
    "com.fire.daily-crypto-rebalance",
    "com.fire.filter-check-equity",
    "com.fire.filter-check-crypto",
]


def _check_launchd_health() -> dict:
    """Check launchctl exit codes for all com.fire.* jobs.

    Returns {"ok": True} when all jobs show exit code 0, or
    {"ok": False, "blocked": [...]} with details for non-zero jobs.
    Exit code 78 (EX_CONFIG) means macOS BTM has disabled the agent.
    """
    try:
        out = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return {"ok": False, "error": "launchctl list failed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    blocked = []
    found_labels = set()
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        label = parts[2]
        if label not in ALL_FIRE_LABELS:
            continue
        found_labels.add(label)
        try:
            exit_code = int(parts[1])
        except ValueError:
            continue
        if exit_code != 0:
            blocked.append({
                "label": label,
                "exit_code": exit_code,
                "reason": "macOS disabled this agent (BTM)" if exit_code == 78 else f"exit code {exit_code}",
            })

    missing = [l for l in ALL_FIRE_LABELS if l not in found_labels]
    for label in missing:
        blocked.append({
            "label": label,
            "exit_code": None,
            "reason": "not registered with launchd",
        })

    return {"ok": len(blocked) == 0, "blocked": blocked}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VALIDATION_STATE_PATH = PROJECT_ROOT / "data" / "risk_state" / "validation_state.json"
VALIDATION_REPORTS_DIR = PROJECT_ROOT / "data" / "validation_reports"

# launchd plists. `schedule` mirrors the plist so the UI can render "next run" without launchctl.
# Schedule shapes: ("daily_local", h, m) | ("daily_utc", h, m) | ("interval_seconds", n)
LAUNCHD_JOBS: list[tuple[str, str, str, tuple]] = [
    # (plist_label, source_tag, expected_scope, schedule)
    ("com.fire.filter-check-equity", "launchd-equity", "spy", ("interval_seconds", 14400)),
    ("com.fire.filter-check-crypto", "launchd-crypto", "btc", ("interval_seconds", 14400)),
]

# launchd-fired rebalance jobs. Last-run state comes from rebalance_log.jsonl
# (filtered by source tag) rather than filter_check.log. Schedule shape
# matches LAUNCHD_JOBS for the `_next_run_iso` helper.
LAUNCHD_REBALANCE_JOBS: list[tuple[str, str, str, str, tuple]] = [
    # (plist_label, job_id, name, journal_source_tag, schedule)
    (
        "com.fire.daily-crypto-rebalance",
        "daily_crypto_rebalance",
        "Daily crypto rebalance (00:05 UTC, launchd)",
        "scheduled",
        ("daily_utc", 0, 5),
    ),
]


def _next_run_iso(schedule: tuple, last_run_local: Optional[datetime]) -> Optional[str]:
    """Compute the next expected fire time for a launchd job, as a UTC ISO string.

    Mirrors the plist contracts in `scripts/com.fire.filter-check-*.plist` so
    the Ops dashboard can show "next run" without `launchctl print` shelling.

    - daily_local(hour, minute): next occurrence of that wall-clock time in
      laptop-local TZ (today if not yet past, otherwise tomorrow). Reflects
      the plist's StartCalendarInterval semantics.
    - daily_utc(hour, minute): same but interpreted in UTC. Reflects a plist
      whose `EnvironmentVariables: TZ=UTC` pins StartCalendarInterval to UTC
      regardless of the laptop's current timezone (used by the daily crypto
      rebalance plist).
    - interval_seconds(s): last_run_local + s. None if we have no last_run
      yet (interval-based plists fire on first load, then every s seconds).
    """
    from datetime import timedelta

    kind = schedule[0]
    if kind == "daily_local":
        _, hour, minute = schedule
        # Plist fires at laptop-local wall-clock time.
        now_local = datetime.now().astimezone()  # aware, local tz
        candidate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now_local:
            candidate = candidate + timedelta(days=1)
        return candidate.astimezone(timezone.utc).isoformat()
    if kind == "daily_utc":
        _, hour, minute = schedule
        now_utc = datetime.now(timezone.utc)
        candidate = now_utc.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now_utc:
            candidate = candidate + timedelta(days=1)
        return candidate.isoformat()
    if kind == "interval_seconds":
        if last_run_local is None:
            return None
        # last_run_local is UTC-aware (from filter_check_log parser).
        candidate = last_run_local + timedelta(seconds=schedule[1])
        return candidate.astimezone(timezone.utc).isoformat()
    return None


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
    """launchd-fired daily rebalance + filter-monitor last-run state.

    Replaces the in-process APScheduler block (retired 2026-05-05). Both
    groups are launchd-driven now; the rebalance group derives last-run
    from the rebalance journal, the monitor group from filter_check.log.
    """
    from data import filter_check_log
    from execution.rebalance_log import get_recent_rebalances

    def _compute():
        # --- Scheduled rebalance block (launchd-fired) ---
        rebalance_runs = get_recent_rebalances(limit=200)
        scheduled_rebalance: dict = {"jobs": []}
        for label, job_id, name, source_tag, schedule in LAUNCHD_REBALANCE_JOBS:
            # Most recent journal entry for this source tag.
            latest = next(
                (r for r in rebalance_runs if r.get("source") == source_tag),
                None,
            )
            if latest is None:
                last_started = None
                last_finished = None
                last_status = None
                error = None
            else:
                last_started = latest.get("timestamp")
                # Journal records one timestamp at write time — use it for
                # both started and finished as a best-effort reconstruction.
                last_finished = latest.get("timestamp")
                execute_error = latest.get("execute_error")
                orders_failed = latest.get("orders_failed", 0) or 0
                if execute_error:
                    last_status = "failed"
                elif orders_failed > 0:
                    # Partial = orders submitted with ≥1 broker rejection
                    # (e.g. expected sub-broker-minimum dust rejections —
                    # see CLAUDE.md). Distinct from "failed".
                    last_status = "partial"
                else:
                    last_status = "success"
                error = execute_error
            scheduled_rebalance["jobs"].append({
                "id": job_id,
                "label": label,
                "name": name,
                "next_run_time": _next_run_iso(schedule, None),
                "last_started": last_started,
                "last_finished": last_finished,
                "last_status": last_status,
                "error": error,
            })

        # --- launchd block (filter monitors) ---
        try:
            runs = filter_check_log.parse_filter_check_log()
        except Exception as e:
            runs = []
            launchd_error = f"log parse failed: {e}"
        else:
            launchd_error = None

        latest = filter_check_log.latest_per_source(runs)
        launchd: list[dict] = []
        for label, source_tag, expected_scope, schedule in LAUNCHD_JOBS:
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
                    "next_run": _next_run_iso(schedule, None),
                })
            else:
                # Log timestamps are naive laptop-local. Localize to UTC
                # so `last_run` serializes with an explicit +00:00 offset,
                # matching the UTC convention used elsewhere (filter_state
                # `last_checked`, rebalance_log timestamps) and letting
                # downstream string comparisons sort correctly.
                utc_started = run.started_at.astimezone(timezone.utc)
                age_s = (datetime.now(timezone.utc) - utc_started).total_seconds()
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
                    "next_run": _next_run_iso(schedule, run.started_at),
                })

        # --- launchd health check (BTM / exit codes) ---
        launchd_health = _check_launchd_health()

        result: dict = {
            "scheduled_rebalance": scheduled_rebalance,
            "launchd": launchd,
            "launchd_health": launchd_health,
        }
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
