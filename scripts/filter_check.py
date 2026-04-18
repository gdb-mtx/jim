#!/usr/bin/env python3
"""Daily filter monitor — detects SPY/BTC filter changes and auto-rebalances.

Designed to run from launchd cron (no server dependency). Checks whether
the SPY 200d MA or BTC 200d MA filter scalar has changed since the last
run, and if so, executes rebalances for affected accounts.

Usage:
    uv run python3 scripts/filter_check.py          # normal run
    uv run python3 scripts/filter_check.py --dry-run # check only, no trades
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.locks import file_rebalance_lock
from data.snapshots import take_snapshot
from execution.alpaca_broker import ACCOUNT_INFO, AlpacaBroker
from execution.rebalance import (
    check_price_staleness,
    compute_rebalance,
    execute_rebalance,
)
from execution.rebalance_log import log_rebalance
from execution.risk_manager import RiskManager
from execution.validation_gate import ValidationGateError, require_validated
from strategies.portfolio import compute_btc_trend_filter, compute_spy_trend_filter

# --- Config ---

STATE_FILE = PROJECT_ROOT / "data" / "risk_state" / "filter_state.json"
LOG_FILE = PROJECT_ROOT / "data" / "filter_check.log"

# Account → filter type
ACCOUNT_FILTERS = {
    1: "spy",
    2: "spy",
    3: "spy",
    4: "btc",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)
log = logging.getLogger("fire.filter_check")


def load_state() -> dict:
    """Load last-known filter state from disk."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    """Write filter state atomically."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    tmp.rename(STATE_FILE)


def compute_filters() -> dict:
    """Compute current SPY and BTC filter scalars."""
    spy_filter = compute_spy_trend_filter()
    btc_filter = compute_btc_trend_filter()

    # Extract price and MA for reporting
    from data.pipeline import download_and_cache
    from data.crypto import download_btc_prices

    spy_prices = download_and_cache(["SPY"], start="2008-01-01", cache_name="spy_filter")
    spy_close = spy_prices["SPY"] if "SPY" in spy_prices.columns else spy_prices.squeeze()
    spy_ma = spy_close.rolling(200).mean()

    btc_prices = download_btc_prices(start="2018-01-01")
    btc_ma = btc_prices.rolling(150).mean()

    return {
        "spy_scalar": float(spy_filter.iloc[-1]),
        "btc_scalar": float(btc_filter.iloc[-1]),
        "spy_price": round(float(spy_close.iloc[-1]), 2),
        "spy_ma200": round(float(spy_ma.iloc[-1]), 2),
        "btc_price": round(float(btc_prices.iloc[-1]), 2),
        "btc_ma150": round(float(btc_ma.iloc[-1]), 2),
    }


def notify(title: str, message: str):
    """Send macOS notification."""
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message}" with title "{title}"',
            ],
            timeout=5,
        )
    except Exception as e:
        log.warning(f"Notification failed: {e}")


def rebalance_account(account: int, dry_run: bool = False) -> dict:
    """Run a full rebalance for one account. Returns result summary."""
    strategy_id = ACCOUNT_INFO[account]["strategy"]
    label = ACCOUNT_INFO[account]["label"]

    log.info(f"  Account {account} ({label}): rebalancing strategy={strategy_id}")

    if dry_run:
        log.info(f"  Account {account}: DRY RUN — skipping execution")
        return {"account": account, "status": "dry_run", "orders": 0}

    try:
        require_validated(account)
    except ValidationGateError as e:
        log.warning(f"  Account {account}: validation gate blocked — {e}")
        return {"account": account, "status": "unvalidated", "orders": 0, "reason": str(e)}

    try:
        with file_rebalance_lock(account):
            broker = AlpacaBroker(account=account)
            risk_mgr = RiskManager(account=account)

            result = compute_rebalance(
                broker=broker,
                strategy_id=strategy_id,
                risk_manager=risk_mgr,
            )

            if result.risk_check.get("portfolio_halted"):
                log.warning(f"  Account {account}: circuit breaker active — skipping")
                return {"account": account, "status": "halted", "orders": 0}

            if result.price_error:
                log.error(f"  Account {account}: missing prices {result.missing_prices}")
                return {"account": account, "status": "price_error", "orders": 0}

            # Price staleness check
            if result.prices:
                drifted = check_price_staleness(broker, result.prices)
                if drifted:
                    log.error(f"  Account {account}: price drift detected: {drifted}")
                    return {"account": account, "status": "price_drift", "orders": 0}

            if not result.orders:
                log.info(f"  Account {account}: no trades needed")
                return {"account": account, "status": "no_trades", "orders": 0}

            # Execute
            order_results = execute_rebalance(broker, result)
            failed = [o for o in order_results if o.get("status") == "error"]

            # Determine filter fields based on account type
            filter_type = ACCOUNT_FILTERS[account]
            log_rebalance(
                account=account,
                strategy_id=strategy_id,
                portfolio_value=result.portfolio_value,
                orders_submitted=len(order_results),
                orders_failed=len(failed),
                order_details=order_results,
                spy_filter_active=result.spy_filter_active,
                spy_filter_scalar=result.spy_filter_scalar,
                btc_filter_active=result.btc_filter_active,
                btc_filter_scalar=result.btc_filter_scalar,
                source="filter_monitor",
            )

            take_snapshot(account)

            log.info(
                f"  Account {account}: {len(order_results)} orders"
                + (f" ({len(failed)} failed)" if failed else "")
            )
            return {
                "account": account,
                "status": "executed",
                "orders": len(order_results),
                "failed": len(failed),
            }

    except OSError:
        log.warning(f"  Account {account}: locked by another process — skipping")
        return {"account": account, "status": "locked", "orders": 0}
    except Exception as e:
        log.error(f"  Account {account}: rebalance failed: {e}", exc_info=True)
        return {"account": account, "status": "error", "error": str(e), "orders": 0}


def main():
    parser = argparse.ArgumentParser(description="FIRE filter monitor")
    parser.add_argument("--dry-run", action="store_true", help="Check only, no trades")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("FIRE Filter Check starting")

    # Load .env for Alpaca credentials
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    # Compute current filter values
    t0 = time.time()
    current = compute_filters()
    log.info(
        f"Filters computed in {time.time() - t0:.1f}s: "
        f"SPY={current['spy_scalar']} (${current['spy_price']} vs MA ${current['spy_ma200']}), "
        f"BTC={current['btc_scalar']} (${current['btc_price']} vs MA ${current['btc_ma150']})"
    )

    # Load previous state
    prev = load_state()
    now = datetime.now(timezone.utc).isoformat()

    # Detect changes
    spy_changed = prev.get("spy_scalar") is not None and current["spy_scalar"] != prev.get("spy_scalar")
    btc_changed = prev.get("btc_scalar") is not None and current["btc_scalar"] != prev.get("btc_scalar")
    first_run = not prev

    if first_run:
        log.info("First run — seeding filter state, no rebalance triggered")
        current["last_checked"] = now
        current["last_spy_change"] = None
        current["last_btc_change"] = None
        save_state(current)
        notify("FIRE Filter Monitor", f"Initialized. SPY={current['spy_scalar']}, BTC={current['btc_scalar']}")
        return

    if not spy_changed and not btc_changed:
        log.info("No filter changes detected")
        prev["last_checked"] = now
        prev.update({
            "spy_price": current["spy_price"],
            "spy_ma200": current["spy_ma200"],
            "btc_price": current["btc_price"],
            "btc_ma150": current["btc_ma150"],
        })
        save_state(prev)
        notify(
            "FIRE Filter Check",
            f"No changes. SPY={'BULL' if current['spy_scalar'] == 1.0 else 'BEAR'}, "
            f"BTC={'BULL' if current['btc_scalar'] == 1.0 else 'BEAR'}",
        )
        return

    # --- Filter changed — rebalance affected accounts ---

    changes = []
    accounts_to_rebalance = []

    if spy_changed:
        direction = "BULLISH" if current["spy_scalar"] == 1.0 else "DEFENSIVE"
        log.info(f"SPY filter changed: {prev.get('spy_scalar')} → {current['spy_scalar']} ({direction})")
        changes.append(f"SPY → {direction}")
        current["last_spy_change"] = now
        accounts_to_rebalance.extend([a for a, f in ACCOUNT_FILTERS.items() if f == "spy"])
    else:
        current["last_spy_change"] = prev.get("last_spy_change")

    if btc_changed:
        direction = "BULLISH" if current["btc_scalar"] == 1.0 else "CASH"
        log.info(f"BTC filter changed: {prev.get('btc_scalar')} → {current['btc_scalar']} ({direction})")
        changes.append(f"BTC → {direction}")
        current["last_btc_change"] = now
        accounts_to_rebalance.extend([a for a, f in ACCOUNT_FILTERS.items() if f == "btc"])
    else:
        current["last_btc_change"] = prev.get("last_btc_change")

    # Execute rebalances
    results = []
    for account in accounts_to_rebalance:
        result = rebalance_account(account, dry_run=args.dry_run)
        results.append(result)

    # Update state
    current["last_checked"] = now
    save_state(current)

    # Summary notification
    executed = [r for r in results if r["status"] == "executed"]
    total_orders = sum(r["orders"] for r in executed)
    change_str = ", ".join(changes)
    if args.dry_run:
        notify("FIRE Filter Monitor (DRY RUN)", f"{change_str}. Would rebalance {len(accounts_to_rebalance)} accounts.")
    elif executed:
        notify("FIRE Filter Monitor", f"{change_str}. Rebalanced {len(executed)} accounts, {total_orders} orders.")
    else:
        skipped = [r for r in results if r["status"] != "executed"]
        notify("FIRE Filter Monitor", f"{change_str}. {len(skipped)} accounts skipped (check log).")

    log.info(f"Filter check complete: {change_str}")
    for r in results:
        log.info(f"  Account {r['account']}: {r['status']} ({r['orders']} orders)")


if __name__ == "__main__":
    main()
