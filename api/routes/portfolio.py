"""Portfolio endpoints — live account data from Alpaca.

Supports 4 paper trading accounts via ?account=1|2|3|4 query param.
Includes equity snapshot storage, correlation monitoring, and risk status.
"""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from execution.alpaca_broker import AlpacaBroker, ACCOUNT_INFO, active_accounts
from execution.risk_manager import RiskManager, RiskLimits, compute_drawdown
from data.snapshots import (
    take_snapshot,
    take_all_snapshots,
    backfill_from_alpaca,
    get_equity_history,
    get_combined_equity_history,
    get_all_equity_histories,
    get_spy_benchmark,
    get_performance_summary,
)
from data.correlation import get_correlation_report

router = APIRouter()

# Per-account broker cache (lazy-init)
_brokers: dict[int, AlpacaBroker] = {}


def _get_broker(account: int) -> AlpacaBroker:
    if account not in _brokers:
        try:
            _brokers[account] = AlpacaBroker(account=account)
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
    return _brokers[account]


@router.get("/accounts")
async def list_accounts():
    """List all configured trading accounts."""
    return [
        {"account": num, **info}
        for num, info in ACCOUNT_INFO.items()
    ]


@router.get("/summary")
async def portfolio_summary(
    account: int = Query(default=1, ge=1, le=4, description="Account number (1-4)"),
):
    """Get account summary — equity, cash, P&L, positions count."""
    broker = _get_broker(account)

    def _compute():
        acct = broker.get_account()
        positions = broker.get_positions()
        total_unrealized_pl = sum(p["unrealized_pl"] for p in positions)
        return {
            **acct,
            "account_number": account,
            "account_label": broker.account_info["label"],
            "default_strategy": broker.account_info["strategy"],
            "positions_count": len(positions),
            "total_unrealized_pl": total_unrealized_pl,
            "market_open": broker.is_market_open(),
        }

    return await asyncio.to_thread(_compute)


@router.get("/positions")
async def portfolio_positions(
    account: int = Query(default=1, ge=1, le=4, description="Account number (1-4)"),
):
    """Get all open positions with P&L details."""
    broker = _get_broker(account)
    return await asyncio.to_thread(broker.get_positions)


@router.get("/combined")
async def combined_summary():
    """Get aggregated summary across all 3 accounts."""
    def _compute():
        all_positions = []
        total_equity = 0
        total_cash = 0
        total_daily_pnl = 0
        total_unrealized_pl = 0
        market_open = False

        active = active_accounts()
        for acct_num in active:
            try:
                broker = _get_broker(acct_num)
                acct = broker.get_account()
                positions = broker.get_positions()
                total_equity += acct["equity"]
                total_cash += acct["cash"]
                total_daily_pnl += acct["daily_pnl"]
                total_unrealized_pl += sum(p["unrealized_pl"] for p in positions)
                market_open = broker.is_market_open()
                for p in positions:
                    p["account"] = acct_num
                    all_positions.append(p)
            except Exception:
                pass

        return {
            "equity": total_equity,
            "cash": total_cash,
            "daily_pnl": total_daily_pnl,
            "total_unrealized_pl": total_unrealized_pl,
            "positions_count": len(all_positions),
            "positions": all_positions,
            "market_open": market_open,
            "accounts": len(active),
        }

    return await asyncio.to_thread(_compute)


@router.get("/value")
async def portfolio_value(
    account: int = Query(default=1, ge=1, le=4, description="Account number (1-4)"),
):
    """Get just the portfolio value (lightweight)."""
    broker = _get_broker(account)
    return {"portfolio_value": await asyncio.to_thread(broker.get_portfolio_value)}


# ── Equity Snapshots & Correlation ───────────────────────────────────


@router.post("/snapshot")
async def create_snapshot(
    account: Optional[int] = Query(default=None, ge=1, le=4, description="Account (1-4) or omit for all"),
):
    """Take an equity snapshot now. Idempotent — skips if today already recorded.

    Also backfills any missing days from Alpaca portfolio history.
    """
    def _compute():
        if account is not None:
            try:
                backfill_from_alpaca(account)
            except Exception:
                pass
            return take_snapshot(account)
        else:
            for acct in active_accounts():
                try:
                    backfill_from_alpaca(acct)
                except Exception:
                    pass
            return take_all_snapshots()

    return await asyncio.to_thread(_compute)


def _patch_today(curve: list[dict], live_equity: float) -> list[dict]:
    """Replace or append today's data point with live equity from Alpaca."""
    from data.trading_dates import today_et

    today = today_et()
    if not curve:
        return [{"time": today, "value": round(live_equity, 2)}]
    if curve[-1]["time"] == today:
        curve[-1] = {"time": today, "value": round(live_equity, 2)}
    else:
        curve.append({"time": today, "value": round(live_equity, 2)})
    return curve


@router.get("/history")
async def equity_history(
    account: int = Query(default=0, ge=0, le=4, description="0=combined, 1-4=individual"),
):
    """Get historical equity time series for charting."""
    def _compute():
        if account == 0:
            histories = get_all_equity_histories()
            combined = get_combined_equity_history()

            # Patch today's values with live Alpaca equity
            total_live = 0.0
            live_equity: dict[int, float] = {}
            for acct_num in active_accounts():
                try:
                    broker = _get_broker(acct_num)
                    live_eq = broker.get_account()["equity"]
                    total_live += live_eq
                    live_equity[acct_num] = live_eq
                    key = f"acct_{acct_num}"
                    if key in histories:
                        histories[key] = _patch_today(histories[key], live_eq)
                except Exception:
                    pass
            if total_live > 0:
                combined = _patch_today(combined, total_live)

            # Normalized SPY benchmark — starts at same value as combined portfolio
            spy_benchmark = []
            if combined:
                dates = [p["time"] for p in combined]
                start_value = combined[0]["value"]
                spy_benchmark = get_spy_benchmark(dates, start_value)
            return {
                "equity_curve": combined,
                "per_account": histories,
                "spy_benchmark": spy_benchmark,
                "performance": get_performance_summary(live_equity or None),
                "days": len(combined),
            }
        else:
            curve = get_equity_history(account)
            try:
                broker = _get_broker(account)
                live_eq = broker.get_account()["equity"]
                curve = _patch_today(curve, live_eq)
            except Exception:
                pass
            return {
                "equity_curve": curve,
                "days": len(curve),
            }

    return await asyncio.to_thread(_compute)


@router.get("/correlation")
async def correlation_data():
    """Get inter-account correlation report for monitoring."""
    return await asyncio.to_thread(get_correlation_report)


# ── Risk / Circuit Breaker Status ─────────────────────────────────


@router.get("/risk")
async def risk_status():
    """Drawdown / halt state for all active accounts.

    Computes drawdown live — pulls current Alpaca equity per account and
    derives the peak from the daily snapshot history (`compute_drawdown`).
    Latches the catastrophe halt here too, so the dashboard stays accurate
    between scheduled rebalances.

    Response schema:
      - halted: bool          — catastrophe halt (-35% DD) latched
      - alert_active: bool    — current DD below -10%
      - drawdown: float       — current DD (negative), e.g. -0.08
      - equity_peak: float    — max(snapshot_history, current_equity)
      - thresholds: {alert, halt}
    """
    limits = RiskLimits()
    thresholds = {
        "alert": limits.portfolio_drawdown_alert,
        "halt": limits.portfolio_drawdown_halt,
    }

    def _per_account(acct_num: int) -> dict:
        base = {"account": acct_num, "label": ACCOUNT_INFO[acct_num]["label"]}
        try:
            broker = _get_broker(acct_num)
            equity = broker.get_portfolio_value()
            dd = compute_drawdown(acct_num, equity, limits)
            rm = RiskManager(account=acct_num, limits=limits)
            rm.check_and_latch_halt(dd.drawdown, dd.equity_peak, equity)
            return {
                **base,
                "halted": rm.halted,
                "alert_active": dd.alert_active,
                "drawdown": dd.drawdown,
                "equity_peak": dd.equity_peak,
            }
        except Exception as e:
            return {
                **base,
                "halted": False,
                "alert_active": False,
                "drawdown": 0.0,
                "equity_peak": 0.0,
                "error": f"Could not compute: {e}",
            }

    accts = active_accounts()
    results = await asyncio.gather(
        *(asyncio.to_thread(_per_account, a) for a in accts)
    )
    accounts = {r["account"]: r for r in results}

    return {
        "any_halted": any(r["halted"] for r in results),
        "any_alert": any(r["alert_active"] for r in results),
        "thresholds": thresholds,
        "accounts": accounts,
    }


@router.post("/risk/reset")
async def reset_circuit_breaker(
    account: int = Query(ge=1, le=4, description="Account number (1-4)"),
):
    """Manually clear the catastrophe halt after review.

    WARNING: Only do this after investigating the drawdown cause.

    Audit trail (R5): appends an entry to `data/rebalance_log.jsonl` with
    `source="halt_reset"` so the reset is visible alongside rebalance events
    in the journal. `was_halted` indicates whether the reset actually did
    something vs. was a no-op.
    """
    import logging
    from execution.rebalance_log import log_rebalance
    log = logging.getLogger("fire.risk")

    def _compute():
        rm = RiskManager(account=account)
        was_halted = rm.halted

        # Best-effort equity pull for the audit record. Reset intent
        # trumps audit detail, so a broker failure doesn't block the reset.
        equity = 0.0
        try:
            broker = _get_broker(account)
            equity = float(broker.get_portfolio_value())
        except Exception as e:
            log.warning(f"halt_reset: could not pull equity for account {account}: {e}")

        rm.reset_halt()

        try:
            log_rebalance(
                account=account,
                strategy_id="(halt reset)",
                portfolio_value=equity,
                orders_submitted=0,
                orders_failed=0,
                order_details=[],
                source="halt_reset",
            )
        except Exception as e:
            log.warning(f"halt_reset: journal append failed for account {account}: {e}")

        return {
            "account": account,
            "was_halted": was_halted,
            "can_trade": rm.can_trade(),
        }

    return await asyncio.to_thread(_compute)


# ── Regime Filter Status ─────────────────────────────────────────


@router.get("/filters")
async def filter_status():
    """Get current regime filter status (SPY 200d MA + BTC 125d MA).

    Uses Alpaca real-time quotes for the current price comparison.
    SPY MA from yfinance cached data; BTC MA from Alpaca bars (broker-native,
    no publishing delay — yfinance had a 1-12h publishing delay on settled
    crypto bars; see HISTORY.md C10).
    """

    def _compute():
        from data.pipeline import download_and_cache
        from data.alpaca_crypto_bars import get_btc_bars
        from data.plausibility import cross_validate_last_close

        result = {}

        try:
            spy_prices = download_and_cache(["SPY"], start="2008-01-01", cache_name="spy_filter").squeeze().dropna()
            spy_ma = spy_prices.rolling(200, min_periods=200).mean()
            spy_ma_val = float(spy_ma.iloc[-1])

            # Use Alpaca real-time price instead of cached yfinance close
            live_spy: float | None = None
            try:
                broker = _get_broker(1)
                live_spy = broker.get_latest_price("SPY")
            except Exception:
                pass

            # Cross-validate cache against live broker quote; >5% divergence flags the cache as suspect.
            if live_spy is not None:
                cross_validate_last_close(spy_prices, "SPY", live_spy)

            spy_price = live_spy if live_spy is not None else float(spy_prices.iloc[-1])

            result["spy"] = {
                "price": round(spy_price, 2),
                "ma_200": round(spy_ma_val, 2),
                "above_ma": spy_price > spy_ma_val,
                "filter_scalar": 1.0 if spy_price > spy_ma_val else 0.5,
            }
        except Exception:
            result["spy"] = {"error": "Could not load SPY data"}

        try:
            btc_prices = get_btc_bars()
            btc_ma = btc_prices.rolling(125, min_periods=125).mean()
            btc_ma_val = float(btc_ma.iloc[-1])

            # Use Alpaca real-time price instead of cached yfinance close
            live_btc: float | None = None
            try:
                broker = _get_broker(4)
                live_btc = broker.get_latest_price("BTC/USD")
            except Exception:
                pass

            # Read-time cross-validation — same pattern as SPY above.
            if live_btc is not None:
                cross_validate_last_close(btc_prices, "BTC-USD", live_btc)

            btc_price = live_btc if live_btc is not None else float(btc_prices.iloc[-1])

            result["btc"] = {
                "price": round(btc_price, 2),
                "ma_125": round(btc_ma_val, 2),
                "above_ma": btc_price > btc_ma_val,
                "filter_scalar": 1.0 if btc_price > btc_ma_val else 0.0,
            }
        except Exception:
            result["btc"] = {"error": "Could not load BTC data"}

        return result

    return await asyncio.to_thread(_compute)


@router.get("/data-freshness")
async def data_freshness():
    """Age and content freshness of each data cache. Dashboard uses this
    to flag two distinct staleness modes:

    - **mtime-stale**: cache file hasn't been re-written in `threshold_h`.
      Means the refresh job is dead. Caught the Mar 10 → Apr 18 2026
      incident where the daily refresh stopped firing entirely.

    - **content-stale**: cache file mtime is fresh but the latest
      *settled* bar inside it is older than expected. Means upstream
      (yfinance) returned incomplete data — the refresh job ran but the
      bar we needed wasn't yet published. Caught (in the future, after
      this fix) the C10 yfinance settled-bar publishing-delay incident
      from 2026-05-06 where the cache held only "two-days-ago + today's
      partial" with yesterday entirely missing.

    The two modes have different remediation: mtime-stale needs the
    cron/launchd job restored, content-stale needs either a later fire
    time or a different data source. Distinguishing them on the
    dashboard makes the diagnostic obvious.

    Content check is asset-class aware:
    - crypto (24/7 markets): latest *settled* bar (i.e. ignoring today's
      partial) should be ≥ yesterday UTC.
    - equity (M-F + holidays): latest bar should be within 4 calendar
      days. The wider window covers weekends + a long weekend's holiday
      without false-positive flagging.
    """
    import time
    import pandas as pd
    from pathlib import Path

    raw_dir = Path(__file__).parent.parent.parent / "data" / "raw"
    # Crypto caches are backtest-only post-2026-05-06 (HISTORY.md C10); equity caches are still live-load-bearing.
    files = [
        {"name": "BTC prices (backtest)",      "file": "btc_prices.parquet",    "threshold_h": 20, "asset_class": "crypto"},
        {"name": "Crypto universe (backtest)", "file": "crypto_prices.parquet", "threshold_h": 20, "asset_class": "crypto"},
        {"name": "VIX",                        "file": "vix.parquet",           "threshold_h": 20, "asset_class": "equity"},
        {"name": "S&P 500",                    "file": "sp500_prices.parquet",  "threshold_h": 30, "asset_class": "equity"},
        {"name": "SPY filter",                 "file": "spy_filter.parquet",    "threshold_h": 20, "asset_class": "equity"},
        {"name": "ETF universe",               "file": "etf_prices.parquet",    "threshold_h": 20, "asset_class": "equity"},
    ]
    now = time.time()
    today_utc = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)
    yesterday_utc = today_utc - pd.Timedelta(days=1)
    # 4 calendar days covers Sat+Sun+Mon-holiday + a buffer day for equity caches
    equity_oldest_acceptable = today_utc - pd.Timedelta(days=4)

    caches = []
    for f in files:
        p = raw_dir / f["file"]
        if not p.exists():
            caches.append({
                "name": f["name"], "file": f["file"], "asset_class": f["asset_class"],
                "age_h": None, "threshold_h": f["threshold_h"],
                "stale": True, "mtime_stale": True, "content_stale": False,
                "latest_bar": None, "missing": True,
            })
            continue

        age_h = (now - p.stat().st_mtime) / 3600
        mtime_stale = age_h > f["threshold_h"]

        # Content check: read the parquet and look at the latest bar date.
        # Drop today's partial bar from consideration (consistent with the
        # C9 fix in CryptoMomentum.generate_signals) — we want to know
        # whether the latest *settled* bar is recent.
        content_stale = False
        latest_bar: Optional[str] = None
        try:
            df = await asyncio.to_thread(pd.read_parquet, p)
            if len(df) > 0:
                latest_ts = pd.Timestamp(df.index[-1])
                if latest_ts >= today_utc and len(df) > 1:
                    latest_ts = pd.Timestamp(df.index[-2])
                latest_bar = latest_ts.strftime("%Y-%m-%d")
                if f["asset_class"] == "crypto":
                    content_stale = latest_ts < yesterday_utc
                else:
                    content_stale = latest_ts < equity_oldest_acceptable
        except Exception:
            # Parquet read failure isn't a freshness issue per se — the
            # schema check in the data layer handles corruption. Don't
            # fail the dashboard endpoint over a single bad file.
            pass

        caches.append({
            "name": f["name"],
            "file": f["file"],
            "asset_class": f["asset_class"],
            "age_h": round(age_h, 1),
            "threshold_h": f["threshold_h"],
            "stale": mtime_stale or content_stale,
            "mtime_stale": mtime_stale,
            "content_stale": content_stale,
            "latest_bar": latest_bar,
            "missing": False,
        })
    any_stale = any(c["stale"] for c in caches)
    return {"any_stale": any_stale, "caches": caches}


@router.post("/refresh-cache")
async def refresh_cache():
    """Force-refresh all data caches including S&P 500 (~30-40s total)."""
    def _refresh():
        from data.pipeline import download_and_cache, EXPANDED_UNIVERSE
        from data.sp500 import download_sp500_prices, download_vix
        from data.crypto import download_crypto_prices, download_btc_prices

        errors = []
        refreshed = []
        for name, fn in [
            ("ETF universe", lambda: download_and_cache(
                EXPANDED_UNIVERSE + ["SHY"], cache_name="etf_prices", force_refresh=True)),
            ("SPY filter", lambda: download_and_cache(
                ["SPY"], cache_name="spy_filter", force_refresh=True)),
            ("VIX", lambda: download_vix(force_refresh=True)),
            ("BTC", lambda: download_btc_prices(force_refresh=True)),
            ("Crypto universe", lambda: download_crypto_prices(force_refresh=True)),
            ("S&P 500", lambda: download_sp500_prices(force_refresh=True)),
        ]:
            try:
                fn()
                refreshed.append(name)
            except Exception as e:
                errors.append(f"{name}: {e}")

        return {"refreshed": refreshed, "errors": errors, "ok": len(errors) == 0}

    return await asyncio.to_thread(_refresh)


@router.get("/filter-state")
async def filter_monitor_state():
    """Get the filter monitor's last-known state and any recent auto-rebalances.

    Reads the state file written by scripts/filter_check.py (cron job).
    Returns null if the monitor has never run.
    """
    from pathlib import Path
    from execution.rebalance_log import get_recent_rebalances

    state_file = Path(__file__).parent.parent.parent / "data" / "risk_state" / "filter_state.json"
    if not state_file.exists():
        return None

    with open(state_file) as f:
        state = json.load(f)

    # Enrich with recent filter_monitor rebalances from the log
    recent = get_recent_rebalances(limit=20)
    monitor_rebalances = [
        r for r in recent if r.get("source") == "filter_monitor"
    ]
    state["recent_auto_rebalances"] = monitor_rebalances[:5]
    return state


@router.get("/plausibility")
async def plausibility_state():
    """Get per-ticker plausibility state and any active issues.

    Returns the raw `plausibility_state.json` (per-ticker last_success /
    last_failure / last_divergence timestamps + values) plus a derived
    `active_issues` list of tickers with:
      - an unresolved write-time failure (last_failure_at > last_success_at), or
      - a recent (<24h) read-time cache-vs-live divergence.

    Dashboard uses `active_issues` to decide whether to show a warning
    banner. Raw state is exposed for debugging.
    """
    from data.plausibility import get_state, has_active_issues

    def _load():
        state = get_state()
        active = has_active_issues(state)
        return {
            "state": state,
            "active_issues": active,
            "has_active": len(active) > 0,
        }

    return await asyncio.to_thread(_load)
