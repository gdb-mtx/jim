#!/usr/bin/env python3
"""Daily filter monitor — detects SPY/BTC filter changes and auto-rebalances.

Designed to run from launchd cron (no server dependency). Checks whether
the SPY 200d MA or BTC 125d MA filter scalar has changed since the last
run, and if so, executes rebalances for affected accounts.

Usage:
    uv run python3 scripts/filter_check.py              # normal: both filters
    uv run python3 scripts/filter_check.py --filter btc # crypto-only run
    uv run python3 scripts/filter_check.py --filter spy # equity-only run
    uv run python3 scripts/filter_check.py --dry-run    # check only, no trades

The two launchd plists invoke this script with different `--filter` scopes
on different cadences (equity at 4:30 PM ET, crypto every 4 hours), so BTC
flips are detected within a few hours instead of once daily. `force_refresh`
is always on here so filter decisions never use a stale cached price.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.locks import file_rebalance_lock
from data import filter_state
from data.snapshots import take_snapshot
from execution.alpaca_broker import ACCOUNT_INFO, AlpacaBroker
from execution.notifications import notify_macos
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

LOG_FILE = PROJECT_ROOT / "data" / "filter_check.log"

# Account → filter type. A3 retired 2026-04-21 (removed from auto-rebalance
# on filter changes). A3's validation_state.json status is "retired" so
# even if this map were wrong, require_validated() would still block.
ACCOUNT_FILTERS = {
    1: "spy",
    2: "spy",
    4: "btc",
}

VALID_SCOPES = ("all", "spy", "btc")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)
log = logging.getLogger("fire.filter_check")


def compute_filters(scope: str = "all") -> dict:
    """Compute current SPY and/or BTC filter scalars.

    `force_refresh=True` on every download so the cached 16h parquet is
    bypassed — filter decisions are always made against a freshly-fetched
    last close. The refresh writes to cache so subsequent non-filter
    readers (dashboard, API) get the up-to-date values too.

    Args:
        scope: "all" | "spy" | "btc" — restrict which filters to compute.
            The crypto-every-4h plist uses scope="btc" to skip the SPY
            download entirely; the equity end-of-day plist uses
            scope="spy".

    Returns:
        Dict with whichever of `spy_*` / `btc_*` fields are in scope.
    """
    from data.pipeline import download_and_cache
    from data.crypto import download_btc_prices

    result: dict = {}

    if scope in ("all", "spy"):
        spy_prices = download_and_cache(
            ["SPY"], start="2008-01-01", cache_name="spy_filter", force_refresh=True
        )
        spy_close = spy_prices["SPY"] if "SPY" in spy_prices.columns else spy_prices.squeeze()
        spy_ma = spy_close.rolling(200).mean()
        spy_filter = compute_spy_trend_filter()
        result.update({
            "spy_scalar": float(spy_filter.iloc[-1]),
            "spy_price": round(float(spy_close.iloc[-1]), 2),
            "spy_ma200": round(float(spy_ma.iloc[-1]), 2),
        })

    if scope in ("all", "btc"):
        btc_prices = download_btc_prices(start="2018-01-01", force_refresh=True)
        btc_ma = btc_prices.rolling(125).mean()
        btc_filter = compute_btc_trend_filter()
        result.update({
            "btc_scalar": float(btc_filter.iloc[-1]),
            "btc_price": round(float(btc_prices.iloc[-1]), 2),
            "btc_ma125": round(float(btc_ma.iloc[-1]), 2),
        })

    return result


def notify(title: str, message: str):
    """Thin wrapper — delegates to the shared `execution.notifications` helper."""
    notify_macos(title, message)


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

            if result.risk_check.get("halted"):
                log.warning(f"  Account {account}: catastrophe halt active — skipping")
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

            # Execute — try/finally so the journal survives any raise (R4)
            order_results: list[dict] = []
            execute_error: str | None = None
            try:
                order_results = execute_rebalance(broker, result)
            except Exception as e:
                execute_error = f"{type(e).__name__}: {e}"
                log.error(f"  Account {account}: execute raised: {execute_error}", exc_info=True)
            finally:
                failed = [o for o in order_results if o.get("status") == "error"]
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
                    vol_scalar=result.vol_scalar,
                    vol_scalar_diagnostics=result.vol_scalar_diagnostics,
                    execute_error=execute_error,
                    source="filter_monitor",
                )

            if execute_error:
                return {"account": account, "status": "execute_error", "orders": len(order_results), "error": execute_error}

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
    parser.add_argument(
        "--filter",
        choices=VALID_SCOPES,
        default="all",
        help="Scope: 'all' (both), 'spy' (equity only), 'btc' (crypto only). "
             "Plists pass 'spy' at 4:30 PM ET and 'btc' every 4h.",
    )
    args = parser.parse_args()

    # Source tag — set by the plist so we can distinguish launchd vs manual
    # runs in the log without relying on time-of-day inference.
    source = os.environ.get("FIRE_FILTER_CHECK_SOURCE", "manual")

    log.info("=" * 60)
    log.info(f"FIRE Filter Check starting (source={source}, scope={args.filter})")

    # Load .env for Alpaca credentials
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    # Compute current filter values (scope-restricted; force_refresh always on)
    t0 = time.time()
    current = compute_filters(scope=args.filter)
    parts = []
    if "spy_scalar" in current:
        parts.append(
            f"SPY={current['spy_scalar']} (${current['spy_price']} vs MA ${current['spy_ma200']})"
        )
    if "btc_scalar" in current:
        parts.append(
            f"BTC={current['btc_scalar']} (${current['btc_price']} vs MA ${current['btc_ma125']})"
        )
    log.info(f"Filters computed in {time.time() - t0:.1f}s: " + ", ".join(parts))

    # Load previous state (uses shared module with file lock; also writes
    # are serialized so the FastAPI APScheduler job can update this file
    # without racing with us).
    prev = filter_state.load()
    first_run = not prev

    # Detect changes — only for scalars in scope
    spy_changed = (
        "spy_scalar" in current
        and prev.get("spy_scalar") is not None
        and current["spy_scalar"] != prev.get("spy_scalar")
    )
    btc_changed = (
        "btc_scalar" in current
        and prev.get("btc_scalar") is not None
        and current["btc_scalar"] != prev.get("btc_scalar")
    )

    if first_run:
        log.info("First run — seeding filter state, no rebalance triggered")
        if not args.dry_run:
            seed = {**current}
            filter_state.save({
                **seed,
                "last_spy_change": None,
                "last_btc_change": None,
            })
        notify("FIRE Filter Monitor", f"Initialized ({args.filter}). {', '.join(parts)}")
        return

    if not spy_changed and not btc_changed:
        log.info("No filter changes detected")
        # Update prices/MAs and last_checked. Only include scope fields so
        # we don't clobber out-of-scope data from the other plist's last run.
        if not args.dry_run:
            filter_state.update_fields(current)
        labels = []
        if "spy_scalar" in current:
            labels.append(f"SPY={'BULL' if current['spy_scalar'] == 1.0 else 'BEAR'}")
        if "btc_scalar" in current:
            labels.append(f"BTC={'BULL' if current['btc_scalar'] == 1.0 else 'BEAR'}")
        notify("FIRE Filter Check", f"No changes. " + ", ".join(labels))
        return

    # --- Filter changed — rebalance affected accounts ---

    changes = []
    accounts_to_rebalance = []

    if spy_changed:
        direction = "BULLISH" if current["spy_scalar"] == 1.0 else "DEFENSIVE"
        log.info(f"SPY filter changed: {prev.get('spy_scalar')} → {current['spy_scalar']} ({direction})")
        changes.append(f"SPY → {direction}")
        accounts_to_rebalance.extend([a for a, f in ACCOUNT_FILTERS.items() if f == "spy"])

    if btc_changed:
        direction = "BULLISH" if current["btc_scalar"] == 1.0 else "CASH"
        log.info(f"BTC filter changed: {prev.get('btc_scalar')} → {current['btc_scalar']} ({direction})")
        changes.append(f"BTC → {direction}")
        accounts_to_rebalance.extend([a for a, f in ACCOUNT_FILTERS.items() if f == "btc"])

    # Execute rebalances
    results = []
    for account in accounts_to_rebalance:
        result = rebalance_account(account, dry_run=args.dry_run)
        results.append(result)

    # Persist the flip. `track_flips` stamps `last_spy_change` /
    # `last_btc_change` when the scalar actually differs.
    if not args.dry_run:
        filter_state.update_fields(
            current,
            track_flips=tuple(k for k in ("spy_scalar", "btc_scalar") if k in current),
        )

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
