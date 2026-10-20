"""Scheduler heartbeat + pre-flight state (2026-10-20).

Two silent-failure modes bit the scheduled rebalance in its first month:
a closed lid at the only fire minute (09-21) and a price cache that
couldn't show the grid bar (10-20). Both looked like health on the Ops
panel — "last run 28d ago, success" — because the panel only knew about
trades. These files make the scheduler's *decisions* visible:

- heartbeat: written on every cron fire (144/day), including crashes.
  Stale (> HEARTBEAT_STALE_S) = cron isn't running the script.
- pre-flight: on the two sessions before a rebalance date the scheduler
  checks the whole chain (validation gate, caches current, ranking dated
  on the grid bar, broker reachable, crontab entry) and records the
  verdict; a change of verdict notifies. The day-before check is the one
  that catches the recurring classes while there is still time to fix.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent.parent / "data" / "risk_state"
HEARTBEAT_PATH = STATE_DIR / "scheduler_heartbeat.json"
PREFLIGHT_PATH = STATE_DIR / "preflight_state.json"
HEARTBEAT_STALE_S = 1800        # three missed 10-minute fires
PREFLIGHT_LOOKAHEAD_SESSIONS = 2
PREFLIGHT_RECHECK_S = 3 * 3600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, payload: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(tmp, path)


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------- heartbeat
def write_heartbeat(decision: str, reason: str, **extra) -> None:
    _write(HEARTBEAT_PATH, {"fired_at": _now(), "decision": decision, "reason": reason, **extra})


def read_heartbeat() -> dict | None:
    hb = _read(HEARTBEAT_PATH)
    if hb is None:
        return None
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(hb["fired_at"])).total_seconds()
    except (KeyError, ValueError):
        age = None
    hb["age_s"] = None if age is None else round(age)
    hb["stale"] = age is None or age > HEARTBEAT_STALE_S
    return hb


# ---------------------------------------------------------------- pre-flight
def upcoming_rebalance(today: str, lookahead: int = PREFLIGHT_LOOKAHEAD_SESSIONS) -> str | None:
    """Next live rebalance date if it is today or within `lookahead` sessions."""
    import pandas as pd
    from data.trading_dates import NYSE_HOLIDAYS, next_live_rebalance_date, live_rebalance_dates

    if today in live_rebalance_dates(today):
        return today
    nxt = next_live_rebalance_date(today)
    sessions = pd.bdate_range(today, nxt, freq="C", holidays=NYSE_HOLIDAYS)
    return nxt if len(sessions) - 1 <= lookahead else None


def crontab_has(marker: str) -> bool:
    try:
        out = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        return out.returncode == 0 and marker in out.stdout
    except Exception:
        return False


def evaluate(checks: list[dict]) -> str:
    """'ok' if every check passed, else 'fail'. checks: [{name, ok, detail}]."""
    return "ok" if all(c["ok"] for c in checks) else "fail"


def should_notify(previous: dict | None, target: str, status: str) -> bool:
    """Notify on the first verdict for a target and on every change after."""
    if previous is None or previous.get("target") != target:
        return True
    return previous.get("notified_status") != status


def recheck_due(previous: dict | None, target: str, grid_bar_present: bool) -> bool:
    """Re-run when the target is new, the last check is old, or the grid bar
    has since landed in the cache (the strongest check only runs then)."""
    if previous is None or previous.get("target") != target:
        return True
    if previous.get("grid_bar_present") != grid_bar_present:
        return True
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(previous["checked_at"])).total_seconds()
    except (KeyError, ValueError):
        return True
    return age > PREFLIGHT_RECHECK_S


def write_preflight(target: str, grid: str, checks: list[dict], grid_bar_present: bool, notified_status: str | None) -> dict:
    state = {
        "target": target, "grid": grid, "checked_at": _now(), "status": evaluate(checks),
        "checks": checks, "grid_bar_present": grid_bar_present, "notified_status": notified_status,
    }
    _write(PREFLIGHT_PATH, state)
    return state


def read_preflight() -> dict | None:
    return _read(PREFLIGHT_PATH)
