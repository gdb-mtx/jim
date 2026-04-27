"""
FastAPI Backend — Serves strategy data to the React dashboard.

Includes APScheduler for daily crypto rebalance at 00:05 UTC.
"""

import asyncio
import logging
import time
import warnings
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import portfolio, orders, ops
from api.research import strategies, backtests
from api.locks import RebalanceLockedError, dual_rebalance_lock

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

log = logging.getLogger("fire.scheduler")

# Module-level scheduler reference so `api/routes/ops.py` can introspect jobs
# and the last-run cache. Assigned inside `lifespan()`; None before startup
# and after shutdown.
scheduler: AsyncIOScheduler | None = None

# In-memory cache of each APScheduler job's last invocation. Reset on server
# restart — the durable record is `data/rebalance_log.jsonl`. Schema:
# {job_id: {"started": iso, "finished": iso|None,
#           "status": "running"|"success"|"skipped"|"failed",
#           "error": str|None}}
_last_run_info: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_run(job_id: str, started: str, status: str, error: str | None = None) -> None:
    """Stamp the end of a job invocation in `_last_run_info`.

    `started` is captured at function entry and threaded through so the
    recorded window reflects the full invocation, not just the terminal
    branch.
    """
    _last_run_info[job_id] = {
        "started": started,
        "finished": _now_iso(),
        "status": status,
        "error": error,
    }


def _backfill_last_run_from_journal() -> None:
    """Populate `_last_run_info["daily_crypto_rebalance"]` from the most
    recent scheduled entry in `rebalance_log.jsonl`.

    Motivation: `_last_run_info` is in-memory only (per design — the
    journal is the durable record). Uvicorn `--reload` wipes it on every
    code change, so the Ops panel's APScheduler row shows "never" after
    any restart until the next 00:05 UTC fire. This backfill closes that
    gap by reconstructing the most recent execution from the journal.

    Limitations: only captures journal-writing outcomes (success +
    execute-time failures). Skip states (validation_gate, locked,
    halted, price_error) and "no trades needed" no-ops don't write to
    the journal, so after a restart the panel shows the most recent
    EXECUTION instead of the most recent attempt. Acceptable — "last
    executed" is the more useful signal, and the miss window is at most
    one day given the 00:05 UTC daily cadence.
    """
    try:
        from execution.rebalance_log import get_recent_rebalances
        for r in get_recent_rebalances(limit=100):
            if r.get("source") != "scheduled":
                continue
            ts = r.get("timestamp")
            if not ts:
                continue
            failed = (
                bool(r.get("execute_error"))
                or (r.get("orders_failed", 0) or 0) > 0
            )
            _last_run_info["daily_crypto_rebalance"] = {
                "started": ts,
                # Journal records one timestamp close to job completion —
                # use it for both started and finished as a best-effort
                # reconstruction. Slightly lossy but good enough for
                # "when did the last scheduled rebalance execute?".
                "finished": ts,
                "status": "failed" if failed else "success",
                "error": r.get("execute_error"),
            }
            log.info(
                f"Backfilled daily_crypto_rebalance last-run from journal: "
                f"{ts} ({'failed' if failed else 'success'})"
            )
            return
        log.info("No scheduled rebalance in journal; last-run stays empty")
    except Exception as e:
        log.warning(f"Journal backfill failed (non-fatal): {e}")


async def _daily_crypto_rebalance():
    """Run daily crypto rebalance for Account 4 at 00:05 UTC.

    Retries up to 3 times with exponential backoff on failure. The outer
    scope records terminal status into `_last_run_info` so the Ops panel
    can render last-run state without tailing the rebalance log.
    """
    from execution.validation_gate import ValidationGateError, require_validated

    job_id = "daily_crypto_rebalance"
    started = _now_iso()
    _last_run_info[job_id] = {
        "started": started,
        "finished": None,
        "status": "running",
        "error": None,
    }

    try:
        require_validated(4)
    except ValidationGateError as e:
        log.warning(f"Daily crypto rebalance blocked by validation gate: {e}")
        _record_run(job_id, started, "skipped", f"validation_gate: {e}")
        return

    max_retries = 3
    final_error: str | None = None
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
                        # try/finally around execute — journal always fires,
                        # even if execute raises mid-flight (R4).
                        order_results: list[dict] = []
                        execute_error: str | None = None
                        try:
                            order_results = await asyncio.to_thread(execute_rebalance, broker, result)
                        except Exception as e:
                            execute_error = f"{type(e).__name__}: {e}"
                            log.error(f"Crypto execute raised: {execute_error}", exc_info=True)
                        finally:
                            failed = [o for o in order_results if o.get("status") == "error"]
                            log.info(
                                f"Crypto rebalance: {len(order_results)} orders submitted"
                                + (f" ({len(failed)} failed)" if failed else "")
                                + (f" [EXECUTE RAISED: {execute_error}]" if execute_error else "")
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
                                raw_signal_weights=result.raw_signal_weights,
                                post_filter_weights=result.post_filter_weights,
                                execute_error=execute_error,
                                source="scheduled",
                                skipped_orders=result.skipped_orders,
                            )

                        if execute_error:
                            # Re-raise so the outer retry loop picks it up.
                            raise RuntimeError(f"execute_rebalance failed: {execute_error}")
                    else:
                        # Distinguish "no drift" from "all drift was dust": if
                        # the engine filtered everything below MIN_NOTIONAL, we
                        # still want a journal entry so the operator can see it.
                        if result.skipped_orders:
                            log.info(
                                f"Crypto rebalance: all {len(result.skipped_orders)} "
                                f"computed order(s) below min-notional — nothing submitted"
                            )
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
                                execute_error=None,
                                source="scheduled",
                                skipped_orders=result.skipped_orders,
                            )
                        else:
                            log.info("Crypto rebalance: no trades needed")

                    await asyncio.to_thread(take_snapshot, 4)

                    # Sync filter_state.json with the live BTC scalar so the
                    # launchd filter monitor doesn't see a stale value later
                    # and fire a no-op second rebalance ("double rebalance"
                    # gap). `update_fields` is file-locked and stamps
                    # `last_btc_flip` only if the scalar actually differs.
                    #
                    # Recompute live instead of using `result.btc_filter_scalar`:
                    # PORTFOLIOS["crypto_momentum_filtered"] has
                    # `btc_filter=False` (filter is internal to CryptoMomentum),
                    # so result.btc_filter_scalar is the default 1.0 even when
                    # BTC is below its 125d MA. Mirrors filter_check.py:
                    # compute_filters.
                    try:
                        from data import filter_state
                        from strategies.portfolio_config import compute_btc_trend_filter
                        live_btc = None
                        try:
                            live_btc = await asyncio.to_thread(broker.get_latest_price, "BTC/USD")
                        except Exception:
                            pass
                        btc_filter = await asyncio.to_thread(compute_btc_trend_filter, live_price=live_btc)
                        btc_scalar = float(btc_filter.iloc[-1])
                        await asyncio.to_thread(
                            filter_state.update_fields,
                            {"btc_scalar": btc_scalar},
                            track_flips=("btc_scalar",),
                        )
                    except Exception as e:
                        log.warning(f"filter_state.json sync failed (non-fatal): {e}")

                    log.info("Daily crypto rebalance complete")
                    _record_run(job_id, started, "success")
                    return  # Success — exit retry loop
            except RebalanceLockedError as e:
                log.warning(f"Crypto rebalance skipped — {e}")
                _record_run(job_id, started, "skipped", f"locked: {e}")
                return

        except Exception as e:
            final_error = f"{type(e).__name__}: {e}"
            log.error(f"Daily crypto rebalance attempt {attempt} failed: {e}", exc_info=True)
            if attempt < max_retries:
                wait = 2 ** attempt * 30  # 60s, 120s
                log.info(f"Retrying in {wait}s...")
                await asyncio.sleep(wait)

    log.error(f"Daily crypto rebalance FAILED after {max_retries} attempts")
    _record_run(job_id, started, "failed", final_error or f"exhausted {max_retries} retries")


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
    global scheduler

    # Run backfill/snapshot in a background thread (non-blocking)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _startup_backfill_and_snapshot)

    # Seed the in-memory last-run cache from the durable journal so dev
    # reloads and production restarts don't flash "never" on the Ops
    # panel's APScheduler row between the restart and the next fire.
    _backfill_last_run_from_journal()

    # Start APScheduler for daily crypto rebalance. Stored on the module
    # global so `api/routes/ops.py` can read `.get_jobs()` / `.running`.
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _daily_crypto_rebalance,
        trigger=CronTrigger(hour=0, minute=5, timezone="UTC"),
        id="daily_crypto_rebalance",
        name="Daily crypto momentum rebalance (00:05 UTC)",
        replace_existing=True,
        # Default APScheduler grace is 1s — any event-loop stall, brief sleep,
        # or worker reload past the cron instant drops the run and advances
        # next_run_time by a full day. 1h absorbs those without ever firing a
        # same-day duplicate (cadence is 24h).
        misfire_grace_time=3600,
    )
    scheduler.start()
    log.info("APScheduler started — crypto rebalance at 00:05 UTC daily")

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    scheduler = None
    log.info("APScheduler stopped")


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
