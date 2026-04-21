"""
Validation Gate — Blocks rebalance execution on unvalidated accounts.

Reads `data/risk_state/validation_state.json` and checks three things
before a rebalance proceeds:
  1. A validation record exists for the account.
  2. The record's status is "pass" or "marginal" (marginal allowed for paper).
  3. The record's `expires` date is in the future (quarterly re-validation).

Status "retired" is an UNCONDITIONAL block — no override can bypass it.
This is deliberate: a retired account should never trade again under any
circumstance, and an accidental `FIRE_VALIDATION_OVERRIDE=1` must not
unblock it (R2, AUDIT_MONTH2).

If any check fails, raise ValidationGateError. Callers translate to a
403 (HTTP) or a graceful abort (scheduled jobs / filter monitor).

Overrides (for FAIL / unvalidated / expired only — never for retired):
  - `FIRE_VALIDATION_OVERRIDE=1` — global (all active accounts).
  - `FIRE_VALIDATION_OVERRIDE_ACCT{N}=1` — scoped to account N (1-4).
Either granting an override surfaces a WARNING log line.
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
OVERRIDE_ENV = "FIRE_VALIDATION_OVERRIDE"  # global
OVERRIDE_PER_ACCT_PREFIX = "FIRE_VALIDATION_OVERRIDE_ACCT"  # + str(N)


def _override_for(account: int) -> bool:
    """True if either the global or the per-account override is set."""
    truthy = ("1", "true", "True")
    if os.environ.get(OVERRIDE_ENV, "") in truthy:
        return True
    if os.environ.get(f"{OVERRIDE_PER_ACCT_PREFIX}{account}", "") in truthy:
        return True
    return False


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
    override = _override_for(account)
    state = _load_state()
    record = state.get(f"account_{account}")

    # RETIRED is an unconditional block — override cannot bypass it.
    # Deliberate: retired accounts must never trade regardless of env flags.
    if record is not None and record.get("status") == "retired":
        msg = (
            f"Account {account} is RETIRED "
            f"(reason: {record.get('retired_reason') or record.get('reason', 'n/a')}). "
            "Retired accounts cannot be overridden — rebalance blocked unconditionally."
        )
        return GateResult(allowed=False, reason=msg, override_active=override, record=record)

    if record is None:
        msg = f"Account {account} has no validation record — run scripts/run_validation.py --account {account}"
        return GateResult(allowed=override, reason=msg, override_active=override, record=None)

    status = record.get("status")
    if status == "fail":
        msg = (
            f"Account {account} validation FAILED "
            f"(reason: {record.get('reason', 'n/a')})"
        )
        return GateResult(allowed=override, reason=msg, override_active=override, record=record)
    if status not in ("pass", "marginal"):
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
