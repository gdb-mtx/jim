"""Pre-rebalance position reconciliation guard.

Compares Alpaca's reported positions against the last-known expected state
saved after a successful rebalance. Detects Alpaca paper trading phantom
position bugs (batch-sync corruption) before we trade on corrupted data.

A mismatch the broker's own ledger explains — a corporate action on that
symbol since the state was saved (merger cash-out, split, symbol change)
— is not a phantom and passes; the state re-baselines at the next
successful execute. Added 2026-09-09 after the EA cash merger (08-14)
silently blocked every Account 2 rebalance for 26 days.

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
    # Mismatches explained by a broker-ledgered corporate action (passed).
    explained: list[dict] = field(default_factory=list)


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
    broker=None,
) -> ReconciliationResult:
    """`broker` (optional, needs .get_corporate_actions) is consulted only
    when a mismatch is found, so the clean path costs no extra API call."""
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

    # A corporate action on the symbol since the state was saved explains
    # any mismatch except a phantom short (no ledger event creates those).
    explained: list[dict] = []
    if mismatches and broker is not None:
        try:
            actions = broker.get_corporate_actions(after=state.get("timestamp", "2020-01-01"))
        except Exception as e:
            log.warning(f"Corporate-action lookup failed for account {account}: {e}")
            actions = []
        by_symbol: dict[str, list[dict]] = {}
        for a in actions:
            by_symbol.setdefault(a.get("symbol"), []).append(a)
        remaining = []
        for m in mismatches:
            hits = by_symbol.get(m["symbol"])
            if hits and m["type"] != "phantom_short":
                # Alpaca ledgers a cash leg and a share leg per event — dedupe.
                m["corporate_action"] = "; ".join(dict.fromkeys(
                    f"{a['activity_type']} {a['date']} {a['description']}".strip() for a in hits
                ))
                explained.append(m)
            else:
                remaining.append(m)
        mismatches = remaining

    if mismatches:
        lines = [f"Account {account} position reconciliation FAILED:"]
        for m in mismatches:
            lines.append(
                f"  {m['symbol']}: {m['type']} — "
                f"broker={m['broker_qty']}, expected={m['expected_qty']}"
                + (f", drift={m['drift_pct']}%" if "drift_pct" in m else "")
            )
        for m in explained:
            lines.append(f"  {m['symbol']}: explained by corporate action ({m['corporate_action']})")
        details = "\n".join(lines)
        log.error(details)
        return ReconciliationResult(
            consistent=False, mismatches=mismatches, details=details, explained=explained
        )

    if explained:
        details = "positions match after corporate actions: " + "; ".join(
            f"{m['symbol']} ({m['corporate_action']})" for m in explained
        )
        log.info(f"Account {account}: {details}")
        return ReconciliationResult(consistent=True, details=details, explained=explained)

    return ReconciliationResult(consistent=True, details="positions match")
