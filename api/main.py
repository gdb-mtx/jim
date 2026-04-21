"""
FastAPI Backend — Serves strategy data to the React dashboard.

Includes APScheduler for daily crypto rebalance at 00:05 UTC.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import portfolio, strategies, backtests, orders
from api.locks import RebalanceLockedError, dual_rebalance_lock

log = logging.getLogger("fire.scheduler")


async def _daily_crypto_rebalance():
    """Run daily crypto rebalance for Account 4 at 00:05 UTC.

    Retries up to 3 times with exponential backoff on failure.
    """
    from execution.validation_gate import ValidationGateError, require_validated

    try:
        require_validated(4)
    except ValidationGateError as e:
        log.warning(f"Daily crypto rebalance blocked by validation gate: {e}")
        return

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            from execution.alpaca_broker import AlpacaBroker
            from execution.rebalance import compute_rebalance, execute_rebalance, check_price_staleness
            from execution.rebalance_log import log_rebalance
            from execution.risk_manager import RiskManager
            from data.snapshots import take_snapshot

            log.info(f"Daily crypto rebalance starting (attempt {attempt}/{max_retries})...")

            try:
                async with dual_rebalance_lock(4):
                    broker = AlpacaBroker(account=4)
                    result = await asyncio.to_thread(
                        compute_rebalance,
                        broker=broker,
                        strategy_id="crypto_momentum_filtered",
                        risk_manager=RiskManager(account=4),
                    )

                    if result.price_error:
                        log.error(f"Crypto rebalance skipped — missing prices: {result.missing_prices}")
                        return

                    if result.risk_check.get("halted"):
                        log.warning("Crypto rebalance skipped — catastrophe halt active")
                        return

                    # Price staleness guard — re-fetch and block on >2% drift
                    if result.prices:
                        drifted = await asyncio.to_thread(check_price_staleness, broker, result.prices)
                        if drifted:
                            raise RuntimeError(f"Price drift detected: {drifted}")

                    if result.orders:
                        order_results = await asyncio.to_thread(execute_rebalance, broker, result)
                        failed = [o for o in order_results if o.get("status") == "error"]
                        log.info(
                            f"Crypto rebalance: {len(order_results)} orders submitted"
                            + (f" ({len(failed)} failed)" if failed else "")
                        )
                        for f in failed:
                            log.error(f"Order failed: {f['symbol']} {f['side']} {f.get('error')}")

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
                            source="scheduled",
                        )
                    else:
                        log.info("Crypto rebalance: no trades needed")

                    await asyncio.to_thread(take_snapshot, 4)
                    log.info("Daily crypto rebalance complete")
                    return  # Success — exit retry loop
            except RebalanceLockedError as e:
                log.warning(f"Crypto rebalance skipped — {e}")
                return

        except Exception as e:
            log.error(f"Daily crypto rebalance attempt {attempt} failed: {e}", exc_info=True)
            if attempt < max_retries:
                wait = 2 ** attempt * 30  # 60s, 120s
                log.info(f"Retrying in {wait}s...")
                await asyncio.sleep(wait)

    log.error(f"Daily crypto rebalance FAILED after {max_retries} attempts")


def _startup_backfill_and_snapshot():
    """Backfill equity history and take today's snapshots for all accounts.

    Runs in a background thread so the server can start accepting requests immediately.
    Also logs the current filter monitor state if available.
    """
    try:
        from data.snapshots import take_all_snapshots, backfill_from_alpaca

        t0 = time.time()
        for acct in (1, 2, 3, 4):
            try:
                added = backfill_from_alpaca(acct)
                if added:
                    log.info(f"Backfilled {added} rows for account {acct}")
            except Exception as e:
                log.warning(f"Backfill account {acct} failed: {e}")
        take_all_snapshots()
        log.info(f"Startup backfill + snapshots done in {time.time() - t0:.1f}s")
    except Exception as e:
        log.error(f"Startup backfill/snapshot failed: {e}", exc_info=True)

    # Log filter monitor state
    try:
        import json
        from pathlib import Path

        state_file = Path(__file__).parent.parent / "data" / "risk_state" / "filter_state.json"
        if state_file.exists():
            with open(state_file) as f:
                state = json.load(f)
            spy_label = "BULLISH" if state.get("spy_scalar") == 1.0 else "DEFENSIVE"
            btc_label = "BULLISH" if state.get("btc_scalar") == 1.0 else "CASH"
            log.info(
                f"Filter monitor state: SPY={spy_label} ({state.get('spy_scalar')}), "
                f"BTC={btc_label} ({state.get('btc_scalar')}), "
                f"last checked {state.get('last_checked', 'never')}"
            )
        else:
            log.info("Filter monitor: no state file (run scripts/filter_check.py to initialize)")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: schedule backfill in background, start crypto scheduler."""
    # Run backfill/snapshot in a background thread (non-blocking)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _startup_backfill_and_snapshot)

    # Start APScheduler for daily crypto rebalance
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _daily_crypto_rebalance,
        trigger=CronTrigger(hour=0, minute=5, timezone="UTC"),
        id="daily_crypto_rebalance",
        name="Daily crypto momentum rebalance (00:05 UTC)",
        replace_existing=True,
    )
    scheduler.start()
    log.info("APScheduler started — crypto rebalance at 00:05 UTC daily")

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    log.info("APScheduler stopped")


app = FastAPI(title="FIRE Trading API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
app.include_router(backtests.router, prefix="/api/backtests", tags=["backtests"])
app.include_router(orders.router, prefix="/api/orders", tags=["orders"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
