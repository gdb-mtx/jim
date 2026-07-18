"""VIXY tail-leg paper pilot — Account 3 (George-approved 2026-07-18).

Converts the tail-insurance question from backtest argument to live track
record at $0 cost: when the VIX9D/VIX3M tail signal flips ON (>= 1.10),
buy VIXY in the idle A3 paper account, sized at PILOT_FRACTION of the
live book (A1+A2 equity); flip OFF -> liquidate. Driven by
scripts/filter_check.py's tail-signal transition handler.

This is a PILOT, not a live strategy: A3 stays "retired" for the
rebalance/validation machinery (the gate guards compute_rebalance; this
module places direct, tightly-guarded orders and is the only thing that
trades A3). Real-money adoption of the tail leg remains a separate George
decision, informed by this pilot's record.

Hard guards: account 3 only, VIXY only, notional capped at MAX_FRACTION
of book, no pyramiding (active position -> entry is a no-op), exit only
sells what exists. Failures never propagate — the caller's filter run
must survive any error here.

State: data/risk_state/tail_leg_state.json
  {active, entry_date, entry_notional, entry_ratio, book_equity_at_entry}
Trade history appends to data/tail_leg_log.jsonl (entry + exit rows, P&L
on exit) for the eventual Q4 review.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("fire.tail_leg")

STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "risk_state" / "tail_leg_state.json"
LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "tail_leg_log.jsonl"
PILOT_ACCOUNT = 3
SYMBOL = "VIXY"
PILOT_FRACTION = 0.05  # of A1+A2 combined equity
MAX_FRACTION = 0.06    # hard cap, belt over the fraction above


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        return {"active": False}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def _append_log(row: dict) -> None:
    row["logged_at"] = datetime.now(timezone.utc).isoformat()
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _book_equity() -> float:
    from execution.alpaca_broker import AlpacaBroker

    total = 0.0
    for acct in (1, 2):
        total += float(AlpacaBroker(account=acct).api.get_account().equity)
    return total


def enter_tail_leg(vix_ratio: float, dry_run: bool = False) -> dict:
    """Buy the pilot VIXY position in A3. No-op if already active."""
    state = _load_state()
    if state.get("active"):
        log.info("tail_leg: already active — no pyramiding, skipping entry")
        return {"status": "already_active"}

    from execution.alpaca_broker import AlpacaBroker

    book = _book_equity()
    notional = round(book * PILOT_FRACTION, 2)
    broker = AlpacaBroker(account=PILOT_ACCOUNT)
    a3_cash = float(broker.api.get_account().cash)
    if notional > book * MAX_FRACTION or notional > a3_cash:
        log.error(f"tail_leg: notional ${notional:,.0f} fails guard (cap "
                  f"${book * MAX_FRACTION:,.0f}, A3 cash ${a3_cash:,.0f}) — aborting")
        return {"status": "guard_blocked", "notional": notional}

    if dry_run:
        log.info(f"tail_leg DRY RUN: would buy ${notional:,.0f} {SYMBOL} in A{PILOT_ACCOUNT}")
        return {"status": "dry_run", "notional": notional}

    order = broker.api.submit_order(
        symbol=SYMBOL, notional=notional, side="buy",
        type="market", time_in_force="day",
    )
    state = {
        "active": True,
        "entry_date": datetime.now(timezone.utc).isoformat(),
        "entry_notional": notional,
        "entry_ratio": vix_ratio,
        "book_equity_at_entry": book,
    }
    _save_state(state)
    _append_log({"event": "entry", "order_id": str(order.id), **state})
    log.warning(f"tail_leg ENTERED: ${notional:,.0f} {SYMBOL} in A{PILOT_ACCOUNT} "
                f"(ratio {vix_ratio}, book ${book:,.0f})")
    return {"status": "entered", "notional": notional}


def exit_tail_leg(vix_ratio: float, dry_run: bool = False) -> dict:
    """Liquidate the pilot VIXY position. No-op if not active/held."""
    state = _load_state()
    from execution.alpaca_broker import AlpacaBroker

    broker = AlpacaBroker(account=PILOT_ACCOUNT)
    held = {p.symbol: p for p in broker.api.list_positions()}
    if SYMBOL not in held:
        if state.get("active"):
            log.warning("tail_leg: state says active but no VIXY held — resetting state")
            _save_state({"active": False})
        return {"status": "nothing_held"}

    pos = held[SYMBOL]
    if dry_run:
        log.info(f"tail_leg DRY RUN: would sell {pos.qty} {SYMBOL} "
                 f"(mkt val ${float(pos.market_value):,.0f})")
        return {"status": "dry_run"}

    order = broker.api.submit_order(
        symbol=SYMBOL, qty=pos.qty, side="sell",
        type="market", time_in_force="day",
    )
    exit_value = float(pos.market_value)
    entry_notional = state.get("entry_notional")
    pnl = (exit_value - entry_notional) if entry_notional else None
    _append_log({
        "event": "exit", "order_id": str(order.id), "exit_ratio": vix_ratio,
        "exit_value": exit_value, "entry_notional": entry_notional,
        "pnl_dollars": round(pnl, 2) if pnl is not None else None,
        "entry_date": state.get("entry_date"),
    })
    _save_state({"active": False})
    log.warning(f"tail_leg EXITED: sold {pos.qty} {SYMBOL} at ~${exit_value:,.0f}"
                + (f", P&L ${pnl:+,.0f}" if pnl is not None else ""))
    return {"status": "exited", "pnl_dollars": pnl}
