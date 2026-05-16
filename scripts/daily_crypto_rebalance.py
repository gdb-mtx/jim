#!/usr/bin/env python3
"""Daily crypto rebalance for Account 4 — fires from launchd at 00:05 UTC.

Replaces the in-process APScheduler job that lived in `api/main.py` until
2026-05-05. APScheduler's AsyncIOScheduler exhibited long-uptime drift
(silent missed fires after several days of uptime); launchd fires
independently of the API server and is the same primitive the filter
monitor already uses reliably.

Synchronous mirror of the original `_daily_crypto_rebalance()` coroutine:
validation gate → file lock (cross-process, non-blocking) → compute →
price-staleness recheck → execute → journal → snapshot → BTC filter_state
sync. Same 3-retry loop with exponential backoff.

Source tag in the journal stays `scheduled` for continuity with historical
entries — downstream queries (Ops dashboard, audit) don't need to change.

Usage:
    uv run python3 scripts/daily_crypto_rebalance.py            # normal
    uv run python3 scripts/daily_crypto_rebalance.py --dry-run  # no orders
"""

import argparse
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.locks import file_rebalance_lock
from data import filter_state
from data.snapshots import take_snapshot
from execution.alpaca_broker import AlpacaBroker
from execution.rebalance import (
    check_price_staleness,
    compute_rebalance,
    execute_rebalance,
)
from execution.rebalance_log import log_rebalance
from execution.risk_manager import RiskManager
from execution.validation_gate import ValidationGateError, require_validated
from strategies.portfolio_config import compute_btc_trend_filter

LOG_FILE = PROJECT_ROOT / "data" / "daily_rebalance.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)
log = logging.getLogger("fire.daily_crypto_rebalance")


def run_once(dry_run: bool = False) -> dict:
    """One attempt of the daily crypto rebalance. Returns result dict.

    Caller drives retries — this function returns the outcome and lets
    `main()` decide whether to retry or give up.
    """
    try:
        require_validated(4)
    except ValidationGateError as e:
        log.warning(f"Blocked by validation gate: {e}")
        return {"status": "skipped", "reason": f"validation_gate: {e}"}

    try:
        with file_rebalance_lock(4):
            broker = AlpacaBroker(account=4)
            risk_mgr = RiskManager(account=4)

            result = compute_rebalance(
                broker=broker,
                strategy_id="crypto_momentum_filtered",
                risk_manager=risk_mgr,
            )

            if result.risk_check.get("halted"):
                log.warning("Catastrophe halt active — skipping")
                return {"status": "halted"}

            if result.position_mismatch:
                log.error("Position reconciliation failed — skipping rebalance")
                log_rebalance(
                    account=4,
                    strategy_id="crypto_momentum_filtered",
                    portfolio_value=result.portfolio_value,
                    orders_submitted=0,
                    orders_failed=0,
                    order_details=[],
                    btc_filter_active=result.btc_filter_active,
                    btc_filter_scalar=result.btc_filter_scalar,
                    vol_scalar=result.vol_scalar,
                    vol_scalar_diagnostics=result.vol_scalar_diagnostics,
                    raw_signal_weights=result.raw_signal_weights,
                    post_filter_weights=result.post_filter_weights,
                    execute_error="position_reconciliation_failed",
                    source="scheduled",
                )
                return {"status": "position_mismatch"}

            if result.price_error:
                log.error(f"Missing prices: {result.missing_prices}")
                return {"status": "price_error", "missing": result.missing_prices}

            if result.prices:
                drifted = check_price_staleness(broker, result.prices)
                if drifted:
                    log.error(f"Price drift detected: {drifted}")
                    return {"status": "price_drift", "drifted": drifted}

            if dry_run:
                log.info(
                    f"DRY RUN — would submit {len(result.orders)} orders "
                    f"(portfolio_value=${result.portfolio_value:,.2f}, "
                    f"btc_filter_scalar={result.btc_filter_scalar}, "
                    f"vol_scalar={result.vol_scalar})"
                )
                for o in result.orders:
                    log.info(f"  {o}")
                return {"status": "dry_run", "orders": len(result.orders)}

            if not result.orders:
                log.info("No trades needed")
                # Still take a snapshot + sync filter_state so a no-op day
                # leaves the same observable state as a trading day.
                take_snapshot(4)
                _sync_btc_filter_state(broker)
                return {"status": "no_trades"}

            order_results: list[dict] = []
            execute_error: str | None = None
            try:
                order_results = execute_rebalance(broker, result)
            except Exception as e:
                execute_error = f"{type(e).__name__}: {e}"
                log.error(f"execute_rebalance raised: {execute_error}", exc_info=True)
            finally:
                failed = [o for o in order_results if o.get("status") == "error"]
                log.info(
                    f"{len(order_results)} orders submitted"
                    + (f" ({len(failed)} failed)" if failed else "")
                    + (f" [EXECUTE RAISED: {execute_error}]" if execute_error else "")
                )
                for f in failed:
                    log.error(f"Order failed: {f.get('symbol')} {f.get('side')} {f.get('error')}")

                log_rebalance(
                    account=4,
                    strategy_id="crypto_momentum_filtered",
                    portfolio_value=result.portfolio_value,
                    orders_submitted=len(order_results),
                    orders_failed=len(failed),
                    order_details=order_results,
                    btc_filter_active=result.btc_filter_active,
                    btc_filter_scalar=result.btc_filter_scalar,
                    vol_scalar=result.vol_scalar,
                    vol_scalar_diagnostics=result.vol_scalar_diagnostics,
                    raw_signal_weights=result.raw_signal_weights,
                    post_filter_weights=result.post_filter_weights,
                    execute_error=execute_error,
                    source="scheduled",
                    prices=result.prices,
                    target_positions=result.target_positions,
                )

            if execute_error:
                # Surface to the retry loop.
                raise RuntimeError(f"execute_rebalance failed: {execute_error}")

            take_snapshot(4)
            _sync_btc_filter_state(broker)

            from execution.position_reconciliation import save_expected_positions
            save_expected_positions(4, result.target_positions or {}, result.portfolio_value)

            return {
                "status": "executed",
                "orders": len(order_results),
                "failed": len(failed),
            }

    except OSError:
        log.warning("Locked by another process — skipping")
        return {"status": "locked"}


def _sync_btc_filter_state(broker: AlpacaBroker) -> None:
    """Update filter_state.json with the current BTC filter scalar so the
    launchd filter monitor doesn't fire a no-op rebalance later from a
    stale value. Mirrors the inline block at the end of the original
    APScheduler job.
    """
    try:
        live_btc = None
        try:
            live_btc = broker.get_latest_price("BTC/USD")
        except Exception:
            pass
        btc_filter = compute_btc_trend_filter(live_price=live_btc)
        btc_scalar = float(btc_filter.iloc[-1])
        filter_state.update_fields(
            {"btc_scalar": btc_scalar},
            track_flips=("btc_scalar",),
        )
    except Exception as e:
        log.warning(f"filter_state.json sync failed (non-fatal): {e}")


def main():
    parser = argparse.ArgumentParser(description="FIRE daily crypto rebalance")
    parser.add_argument("--dry-run", action="store_true", help="Compute orders, skip execution")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info(f"Daily crypto rebalance starting (dry_run={args.dry_run})")

    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    max_retries = 3
    final_result: dict = {"status": "unknown"}
    for attempt in range(1, max_retries + 1):
        log.info(f"Attempt {attempt}/{max_retries}")
        try:
            final_result = run_once(dry_run=args.dry_run)
            # Terminal outcomes that retry won't fix.
            if final_result["status"] in (
                "executed", "no_trades", "dry_run",
                "skipped", "halted", "locked", "position_mismatch",
            ):
                break
            # Retry-worthy outcomes: price_error, price_drift, transient raises.
            if attempt < max_retries:
                wait = 2 ** attempt * 30  # 60s, 120s
                log.info(f"Outcome={final_result['status']} — retrying in {wait}s")
                time.sleep(wait)
        except Exception as e:
            log.error(f"Attempt {attempt} raised: {e}", exc_info=True)
            final_result = {"status": "error", "error": str(e)}
            if attempt < max_retries:
                wait = 2 ** attempt * 30
                log.info(f"Retrying in {wait}s")
                time.sleep(wait)

    log.info(f"Final outcome: {final_result}")
    # launchd doesn't act on exit codes for Calendar-triggered jobs, but
    # nonzero on hard failure makes the stderr log easier to scan.
    sys.exit(0 if final_result.get("status") in (
        "executed", "no_trades", "dry_run", "skipped", "halted", "locked"
    ) else 1)


if __name__ == "__main__":
    main()
