"""Shared accessor for `data/risk_state/filter_state.json`.

Multiple processes + multiple schedules write to this file:
- `scripts/filter_check.py` invoked by launchd (equity plist at 4:30 PM ET
  and crypto plist every 4h).
- The FastAPI APScheduler job for A4 also updates it after a successful
  daily crypto rebalance, so the state file never lags a filter flip that
  the server acted on (closes the "double rebalance" gap where launchd
  would otherwise re-fire against the same flip hours later).

Concurrent access is serialized via a `fcntl` file lock, and every write
goes through an atomic tmp-file rename. Read-modify-write callers should
use `update_fields` so the lock scope covers the whole R-M-W.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "risk_state" / "filter_state.json"
_LOCK_PATH = STATE_PATH.with_suffix(".lock")


@contextmanager
def _file_lock(timeout: float = 5.0):
    """Blocking exclusive lock on `filter_state.lock`.

    Separate from the data file so `os.replace` on the data file isn't
    confused by a held lock descriptor.
    """
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(_LOCK_PATH), os.O_CREAT | os.O_RDWR)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load() -> dict[str, Any]:
    """Return the current filter state dict (empty if file missing/unreadable)."""
    if not STATE_PATH.exists():
        return {}
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def load_with_plausibility() -> dict[str, Any]:
    """Return filter state enriched with plausibility snapshot.

    Used by `/api/ops/filters` so the Ops panel can render filter status and
    any active data-quality issues (cached-vs-live divergences, write-time
    band failures) in a single response.

    Plausibility state lives separately in `data/plausibility.py` and is
    imported lazily here to keep `data.filter_state` free of pandas-touching
    dependencies at import time.
    """
    from data import plausibility

    state = load()
    plaus_state = plausibility.get_state()
    active = plausibility.has_active_issues(plaus_state)
    state["plausibility"] = {
        "state": plaus_state,
        "active_issues": active,
        "has_active": bool(active),
    }
    return state


def _atomic_write(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, STATE_PATH)


def save(state: dict[str, Any]) -> None:
    """Atomically replace the state file with the given dict (locked)."""
    with _file_lock():
        _atomic_write(state)


def update_fields(
    updates: dict[str, Any],
    *,
    set_last_checked: bool = True,
    track_flips: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Lock-read-merge-write the state file and return the new state.

    Args:
        updates: Fields to set on the state dict (e.g. current scalars/prices).
        set_last_checked: If True, stamp `last_checked` to now (UTC ISO).
        track_flips: Scalar field names to compare against existing state.
            For every field in this tuple whose value in `updates` differs
            from the existing stored value, also write
            `last_{field}_change = now`. Use this so both writers (launchd
            filter_check.py and APScheduler) can record a flip timestamp
            uniformly without racing.

    Returns:
        The merged state dict after the write.
    """
    with _file_lock():
        state = load()
        now = _now_iso()
        for key in track_flips:
            new_val = updates.get(key)
            old_val = state.get(key)
            if new_val is not None and old_val is not None and new_val != old_val:
                # Convention: scalar field `btc_scalar` -> flip field `last_btc_change`.
                prefix = key.replace("_scalar", "")
                state[f"last_{prefix}_change"] = now
        state.update(updates)
        if set_last_checked:
            state["last_checked"] = now
        _atomic_write(state)
        return state
