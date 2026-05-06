"""
FastAPI Backend — Serves strategy data to the React dashboard.

The daily crypto rebalance for Account 4 used to live here as an
in-process APScheduler job. It was retired on 2026-05-05 after a
long-uptime drift incident: APScheduler's AsyncIOScheduler silently
missed a fire after 5 days of uptime — the kind of failure mode an
in-process scheduler is structurally exposed to. The job now runs
via launchd (`scripts/com.fire.daily-crypto-rebalance.plist` →
`scripts/daily_crypto_rebalance.py`), the same primitive the filter
monitor already uses reliably. Post-Fly migration target is Fly Cron
Machines (DEPLOYMENT_PLAN.md).
"""

import asyncio
import logging
import time
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import portfolio, orders, ops
from api.research import strategies, backtests

# Silence yfinance's pandas Timestamp.utcnow() deprecation spam. This MUST
# come AFTER the imports above — yfinance registers its own
# `('default', DeprecationWarning, '^yfinance')` filter at import time, and
# `warnings.filterwarnings` prepends to the filter list. If we set our
# filter first, yfinance's filter ends up ahead of ours and wins (first
# match emits). Setting it last puts our ignore-rule at the head of the
# list so it fires before yfinance's default-action filter.
#
# REMOVE THIS FILTER when yfinance migrates to Timestamp.now('UTC').
# If pandas 5.0 is bumped before yfinance ships the fix, this filter becomes
# a no-op and the underlying AttributeError will surface immediately — which
# is the safer failure mode. uv.lock pins both packages, so the bite can
# only happen when we deliberately upgrade pandas across major versions;
# coordinate that with a yfinance bump.
warnings.filterwarnings(
    "ignore",
    message=r"Timestamp\.utcnow is deprecated.*",
)

log = logging.getLogger("fire.api")


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
    """Startup: schedule backfill in background. No in-process scheduler —
    daily crypto rebalance is fired by launchd (see module docstring)."""
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _startup_backfill_and_snapshot)
    yield


app = FastAPI(title="FIRE Trading API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
app.include_router(backtests.router, prefix="/api/backtests", tags=["backtests"])
app.include_router(orders.router, prefix="/api/orders", tags=["orders"])
app.include_router(ops.router, prefix="/api/ops", tags=["ops"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
