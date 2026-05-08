"""Pre-rebalance position reconciliation guard.

Compares Alpaca's reported positions against the last-known expected state
saved after a successful rebalance. Detects Alpaca paper trading phantom
position bugs (batch-sync corruption) before we trade on corrupted data.

State file: data/risk_state/expected_positions_acct{N}.json
Override: FIRE_SKIP_RECONCILIATION=1 to bypass (for manual recovery)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("fire.reconciliation")

STATE_DIR = Path(__file__).resolve().parent.parent / "data" / "risk_state"


@dataclass
class ReconciliationResult:
    consistent: bool
    mismatches: list[dict] = field(default_factory=list)
    details: str = ""


def _state_path(account: int) -> Path:
    return STATE_DIR / f"expected_positions_acct{account}.json"


def save_expected_positions(
    account: int,
    positions: dict[str, float],
    portfolio_value: float | None = None,
) -> None:
    path = _state_path(account)
    state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "positions": positions,
    }
    if portfolio_value is not None:
        state["portfolio_value"] = round(portfolio_value, 2)
    path.write_text(json.dumps(state, indent=2) + "\n")
    log.info(f"Saved expected positions for account {account}: {list(positions.keys())}")


def check_position_consistency(
    account: int,
    broker_positions: dict[str, float],
    prices: dict[str, float] | None = None,
    qty_tolerance: float = 0.05,
) -> ReconciliationResult:
    if os.environ.get("FIRE_SKIP_RECONCILIATION"):
        log.warning("FIRE_SKIP_RECONCILIATION set — bypassing reconciliation")
        return ReconciliationResult(consistent=True, details="skipped (override)")

    path = _state_path(account)
    if not path.exists():
        log.info(f"No expected-positions state for account {account} — first run, passing")
        return ReconciliationResult(consistent=True, details="no prior state")

    try:
        state = json.loads(path.read_text())
        expected = state["positions"]
    except (json.JSONDecodeError, KeyError) as e:
        log.warning(f"Corrupt expected-positions state for account {account}: {e}")
        return ReconciliationResult(consistent=True, details="corrupt state file, passing")

    mismatches: list[dict] = []
    all_symbols = set(list(broker_positions.keys()) + list(expected.keys()))

    for symbol in all_symbols:
        broker_qty = broker_positions.get(symbol, 0.0)
        expected_qty = expected.get(symbol, 0.0)

        if broker_qty < 0:
            mismatches.append({
                "symbol": symbol,
                "type": "phantom_short",
                "broker_qty": broker_qty,
                "expected_qty": expected_qty,
            })
            continue

        if symbol not in expected and broker_qty != 0:
            is_dust = prices and symbol in prices and abs(broker_qty * prices[symbol]) < 10
            if not is_dust:
                mismatches.append({
                    "symbol": symbol,
                    "type": "unexpected",
                    "broker_qty": broker_qty,
                    "expected_qty": 0,
                })
            continue

        if symbol not in broker_positions and expected_qty != 0:
            is_dust = prices and symbol in prices and abs(expected_qty * prices[symbol]) < 10
            if not is_dust:
                mismatches.append({
                    "symbol": symbol,
                    "type": "missing",
                    "broker_qty": 0,
                    "expected_qty": expected_qty,
                })
            continue

        if expected_qty == 0:
            continue

        drift = abs(broker_qty - expected_qty) / abs(expected_qty)
        if drift > qty_tolerance:
            mismatches.append({
                "symbol": symbol,
                "type": "qty_drift",
                "broker_qty": broker_qty,
                "expected_qty": expected_qty,
                "drift_pct": round(drift * 100, 1),
            })

    if mismatches:
        lines = [f"Account {account} position reconciliation FAILED:"]
        for m in mismatches:
            lines.append(
                f"  {m['symbol']}: {m['type']} — "
                f"broker={m['broker_qty']}, expected={m['expected_qty']}"
                + (f", drift={m['drift_pct']}%" if "drift_pct" in m else "")
            )
        details = "\n".join(lines)
        log.error(details)
        return ReconciliationResult(consistent=False, mismatches=mismatches, details=details)

    return ReconciliationResult(consistent=True, details="positions match")
