"""
Validation Gate — Blocks rebalance execution on unvalidated accounts.

Reads `data/risk_state/validation_state.json` and checks three things
before a rebalance proceeds:
  1. A validation record exists for the account.
  2. The record's status is "pass".
  3. The record's `expires` date is in the future (quarterly re-validation).

If any check fails, raise ValidationGateError. Callers translate to a
403 (HTTP) or a graceful abort (scheduled jobs / filter monitor).

Override: set `FIRE_VALIDATION_OVERRIDE=1` to bypass. Intentional
friction — the dashboard should show a warning banner when set.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

log = logging.getLogger("fire.validation_gate")

STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "risk_state" / "validation_state.json"
OVERRIDE_ENV = "FIRE_VALIDATION_OVERRIDE"


class ValidationGateError(RuntimeError):
    """Raised when the validation gate blocks a rebalance."""

    def __init__(self, message: str, detail: dict):
        super().__init__(message)
        self.detail = detail


@dataclass
class GateResult:
    allowed: bool
    reason: str
    override_active: bool
    record: dict | None


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception as e:
        log.warning(f"validation_state.json unreadable: {e}; treating as empty")
        return {}


def check(account: int) -> GateResult:
    """Return a GateResult for the given account — does not raise.

    Caller decides how to surface the block. The endpoint raises HTTPException,
    the scheduler logs and returns, etc.
    """
    override = os.environ.get(OVERRIDE_ENV, "") in ("1", "true", "True")
    state = _load_state()
    record = state.get(f"account_{account}")

    if record is None:
        msg = f"Account {account} has no validation record — run scripts/run_validation.py --account {account}"
        return GateResult(allowed=override, reason=msg, override_active=override, record=None)

    status = record.get("status")
    if status != "pass":
        msg = (
            f"Account {account} validation status is {status!r} "
            f"(reason: {record.get('reason', 'n/a')})"
        )
        return GateResult(allowed=override, reason=msg, override_active=override, record=record)

    expires_str = record.get("expires")
    if expires_str:
        try:
            if date.fromisoformat(expires_str) < date.today():
                msg = (
                    f"Account {account} validation expired {expires_str} — re-run "
                    f"scripts/run_validation.py --account {account}"
                )
                return GateResult(allowed=override, reason=msg, override_active=override, record=record)
        except ValueError:
            pass

    return GateResult(allowed=True, reason="validated", override_active=override, record=record)


def require_validated(account: int) -> GateResult:
    """Convenience wrapper: call `check`, raise ValidationGateError if blocked.

    Returns the GateResult on success (useful for logging override use).
    """
    result = check(account)
    if not result.allowed:
        raise ValidationGateError(
            result.reason,
            detail={"account": account, "record": result.record, "override": result.override_active},
        )
    if result.override_active and result.reason != "validated":
        log.warning(
            f"VALIDATION OVERRIDE ACTIVE for account {account}: {result.reason}"
        )
    return result
