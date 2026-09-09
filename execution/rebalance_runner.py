"""One guarded rebalance for one account — the shared path for every
unattended caller (filter monitor flips, the scheduled 21-day rebalance).

Validation gate → per-account file lock → compute (reconciliation, halt,
prices) → price-staleness recheck → execute → journal (always, even on a
raise) → snapshot → expected-positions baseline. Extracted from
scripts/filter_check.py on 2026-09-09 when the scheduled rebalance needed
the identical path under a different journal source tag.
"""

import logging

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

_default_log = logging.getLogger("fire.rebalance_runner")


def rebalance_account(
    account: int,
    *,
    source: str,
    dry_run: bool = False,
    log: logging.Logger | None = None,
) -> dict:
    """Run a full rebalance for one account. Returns a result summary dict
    whose `status` is one of: dry_run, unvalidated, halted, position_mismatch,
    price_error, price_drift, no_trades, executed, execute_error, locked, error.
    """
    log = log or _default_log
    strategy_id = ACCOUNT_INFO[account]["strategy"]
    label = ACCOUNT_INFO[account]["label"]

    log.info(f"  Account {account} ({label}): rebalancing strategy={strategy_id} source={source}")

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

            if result.position_mismatch:
                log.error(f"  Account {account}: position reconciliation failed — skipping")
                return {"account": account, "status": "position_mismatch", "orders": 0,
                        "reason": result.position_mismatch_details}

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
                    raw_signal_weights=result.raw_signal_weights,
                    post_filter_weights=result.post_filter_weights,
                    execute_error=execute_error,
                    source=source,
                    prices=result.prices,
                    target_positions=result.target_positions,
                    signal_asof=result.signal_asof,
                )

            if execute_error:
                return {"account": account, "status": "execute_error",
                        "orders": len(order_results), "error": execute_error}

            take_snapshot(account)

            from execution.position_reconciliation import save_expected_positions
            save_expected_positions(account, result.target_positions or {}, result.portfolio_value)

            log.info(
                f"  Account {account}: {len(order_results)} orders"
                + (f" ({len(failed)} failed)" if failed else "")
            )
            return {
                "account": account,
                "status": "executed",
                "orders": len(order_results),
                "failed": len(failed),
                "signal_asof": result.signal_asof,
            }

    except OSError:
        log.warning(f"  Account {account}: locked by another process — skipping")
        return {"account": account, "status": "locked", "orders": 0}
    except Exception as e:
        log.error(f"  Account {account}: rebalance failed: {e}", exc_info=True)
        return {"account": account, "status": "error", "error": str(e), "orders": 0}
