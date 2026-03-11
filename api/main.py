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
from api.locks import get_rebalance_lock

log = logging.getLogger("fire.scheduler")


async def _daily_crypto_rebalance():
    """Run daily crypto rebalance for Account 4 at 00:05 UTC.

    Retries up to 3 times with exponential backoff on failure.
    """
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            from execution.alpaca_broker import AlpacaBroker
            from execution.rebalance import compute_rebalance, execute_rebalance
            from execution.rebalance_log import log_rebalance
            from execution.risk_manager import RiskManager
            from data.snapshots import take_snapshot

            log.info(f"Daily crypto rebalance starting (attempt {attempt}/{max_retries})...")

            lock = get_rebalance_lock(4)
            if lock.locked():
                log.warning("Crypto rebalance skipped — another rebalance already running")
                return

            async with lock:
                broker = AlpacaBroker(account=4)
                result = compute_rebalance(
                    broker=broker,
                    strategy_id="crypto_momentum_filtered",
                    risk_manager=RiskManager(account=4),
                )

                if result.risk_check.get("portfolio_halted"):
                    log.warning("Crypto rebalance skipped — circuit breaker active")
                    return

                if result.orders:
                    order_results = execute_rebalance(broker, result)
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
                        source="scheduled",
                    )
                else:
                    log.info("Crypto rebalance: no trades needed")

                take_snapshot(4)
                log.info("Daily crypto rebalance complete")
                return  # Success — exit retry loop

        except Exception as e:
            log.error(f"Daily crypto rebalance attempt {attempt} failed: {e}", exc_info=True)
            if attempt < max_retries:
                wait = 2 ** attempt * 30  # 60s, 120s
                log.info(f"Retrying in {wait}s...")
                await asyncio.sleep(wait)

    log.error(f"Daily crypto rebalance FAILED after {max_retries} attempts")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: backfill + snapshot all accounts, start crypto scheduler."""
    # Backfill and snapshot
    try:
        from data.snapshots import take_all_snapshots, backfill_from_alpaca

        for acct in (1, 2, 3, 4):
            try:
                backfill_from_alpaca(acct)
            except Exception:
                pass
        take_all_snapshots()
    except Exception as e:
        print(f"Snapshot on startup skipped: {e}")

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
