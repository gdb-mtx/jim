#!/usr/bin/env python3
"""Liquidate all positions on an Alpaca paper account.

Used for retiring a strategy from a live account while preserving the
Alpaca account slot for a future strategy assignment. Cancels any open
orders, then submits market orders to close every position.

Usage:
    uv run python3 scripts/liquidate_account.py --account 3 --dry-run
    uv run python3 scripts/liquidate_account.py --account 3 --confirm

Requires --confirm to actually submit orders. Without --confirm or with
--dry-run, prints what would happen and exits.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.locks import file_rebalance_lock
from execution.alpaca_broker import ACCOUNT_INFO, AlpacaBroker
from execution.rebalance_log import log_rebalance

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("fire.liquidate")


def main() -> int:
    parser = argparse.ArgumentParser(description="Liquidate all positions on one account")
    parser.add_argument("--account", type=int, required=True, choices=[1, 2, 3, 4])
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no orders")
    parser.add_argument("--confirm", action="store_true", help="Required to actually submit orders")
    args = parser.parse_args()

    # Load .env for Alpaca credentials
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    info = ACCOUNT_INFO[args.account]
    label = info.get("label", "?")
    strategy_id = info.get("strategy") or "none"

    log.info("=" * 60)
    log.info(f"Liquidating account {args.account} ({info['name']} — {label})")
    log.info(f"Current strategy field: {strategy_id}")

    broker = AlpacaBroker(account=args.account)
    positions = broker.get_positions()
    portfolio_value = broker.get_portfolio_value()
    cash = broker.get_cash()

    log.info(f"Portfolio value: ${portfolio_value:,.2f}  |  Cash: ${cash:,.2f}")
    log.info(f"Positions to close: {len(positions)}")
    if not positions:
        log.info("No positions to close. Exiting.")
        return 0

    for p in positions:
        log.info(
            f"  {p['symbol']:<8} qty={p['qty']}  "
            f"mv=${p.get('market_value', 0):,.2f}  "
            f"pl=${p.get('unrealized_pl', 0):,.2f}"
        )

    if args.dry_run or not args.confirm:
        log.info("DRY RUN — pass --confirm to execute. No orders submitted.")
        return 0

    # Acquire the same cross-process lock rebalance uses, so we can't race
    # a scheduled rebalance on the same account.
    try:
        with file_rebalance_lock(args.account):
            log.info("Cancelling any open orders...")
            cancelled = broker.cancel_all_orders()
            log.info(f"Cancelled {cancelled} open orders")

            log.info("Submitting close orders for all positions...")
            results = broker.close_all_positions(cancel_open_orders=False)
            failed = [r for r in results if r.get("http_status") and r["http_status"] >= 400]

            for r in results:
                sym = r.get("symbol") or "?"
                side = r.get("side") or "?"
                qty = r.get("qty") or "?"
                status = r.get("status") or "?"
                http_status = r.get("http_status")
                log.info(
                    f"  {sym:<8} side={side} qty={qty} "
                    f"status={status} http={http_status}"
                )

            log_rebalance(
                account=args.account,
                strategy_id=f"liquidate:{strategy_id}",
                portfolio_value=portfolio_value,
                orders_submitted=len(results),
                orders_failed=len(failed),
                order_details=results,
                source="liquidate_account",
            )

            log.info(
                f"Liquidation submitted: {len(results)} close orders "
                f"({len(failed)} errored). Fills will settle over the next few seconds."
            )
    except OSError:
        log.error(f"Account {args.account} is locked by another process. Aborting.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
