"""Portfolio endpoints — live account data from Alpaca.

Supports 4 paper trading accounts via ?account=1|2|3|4 query param.
Includes equity snapshot storage, correlation monitoring, and risk status.
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from execution.alpaca_broker import AlpacaBroker, ACCOUNT_INFO
from execution.risk_manager import RiskManager, STATE_DIR
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


@router.get("/positions")
async def portfolio_positions(
    account: int = Query(default=1, ge=1, le=4, description="Account number (1-4)"),
):
    """Get all open positions with P&L details."""
    broker = _get_broker(account)
    return broker.get_positions()


@router.get("/combined")
async def combined_summary():
    """Get aggregated summary across all 3 accounts."""
    all_positions = []
    total_equity = 0
    total_cash = 0
    total_daily_pnl = 0
    total_unrealized_pl = 0
    market_open = False

    for acct_num in ACCOUNT_INFO:
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
        "accounts": len(ACCOUNT_INFO),
    }


@router.get("/value")
async def portfolio_value(
    account: int = Query(default=1, ge=1, le=4, description="Account number (1-4)"),
):
    """Get just the portfolio value (lightweight)."""
    broker = _get_broker(account)
    return {"portfolio_value": broker.get_portfolio_value()}


# ── Equity Snapshots & Correlation ───────────────────────────────────


@router.post("/snapshot")
async def create_snapshot(
    account: Optional[int] = Query(default=None, ge=1, le=4, description="Account (1-4) or omit for all"),
):
    """Take an equity snapshot now. Idempotent — skips if today already recorded.

    Also backfills any missing days from Alpaca portfolio history.
    """
    if account is not None:
        try:
            backfill_from_alpaca(account)
        except Exception:
            pass
        return take_snapshot(account)
    else:
        for acct in ACCOUNT_INFO:
            try:
                backfill_from_alpaca(acct)
            except Exception:
                pass
        return take_all_snapshots()


def _patch_today(curve: list[dict], live_equity: float) -> list[dict]:
    """Replace or append today's data point with live equity from Alpaca."""
    from datetime import date

    today = date.today().isoformat()
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
    if account == 0:
        histories = get_all_equity_histories()
        combined = get_combined_equity_history()

        # Patch today's values with live Alpaca equity
        total_live = 0.0
        live_equity: dict[int, float] = {}
        for acct_num in ACCOUNT_INFO:
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


@router.get("/correlation")
async def correlation_data():
    """Get inter-account correlation report for monitoring."""
    return get_correlation_report()


# ── Risk / Circuit Breaker Status ─────────────────────────────────


@router.get("/risk")
async def risk_status():
    """Get circuit breaker state for all accounts.

    Reads persisted state files — no Alpaca API calls needed.
    """
    accounts = {}
    any_halted = False

    for acct_num in ACCOUNT_INFO:
        state_file = STATE_DIR / f"circuit_breaker_acct{acct_num}.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
                halted = data.get("halted", False)
                if halted:
                    any_halted = True
                accounts[acct_num] = {
                    "account": acct_num,
                    "label": ACCOUNT_INFO[acct_num]["label"],
                    "halted": halted,
                    "equity_peak": data.get("equity_peak", 0),
                    "halted_strategies": data.get("halted_strategies", []),
                    "strategy_peaks": data.get("strategy_peaks", {}),
                }
            except (json.JSONDecodeError, OSError):
                accounts[acct_num] = {
                    "account": acct_num,
                    "label": ACCOUNT_INFO[acct_num]["label"],
                    "halted": False,
                    "error": "Could not read state file",
                }
        else:
            accounts[acct_num] = {
                "account": acct_num,
                "label": ACCOUNT_INFO[acct_num]["label"],
                "halted": False,
                "equity_peak": 0,
                "halted_strategies": [],
            }

    return {
        "any_halted": any_halted,
        "accounts": accounts,
    }


@router.post("/risk/reset")
async def reset_circuit_breaker(
    account: int = Query(ge=1, le=4, description="Account number (1-4)"),
    strategy: Optional[str] = Query(default=None, description="Strategy name to reset, or omit for portfolio-level"),
):
    """Manually reset a circuit breaker after review.

    WARNING: Only do this after investigating the drawdown cause.
    """
    rm = RiskManager(account=account)
    rm.reset_halt(strategy)

    return {
        "account": account,
        "reset": strategy or "portfolio",
        "can_trade": rm.can_trade(strategy),
    }


# ── Regime Filter Status ─────────────────────────────────────────


@router.get("/filters")
async def filter_status():
    """Get current regime filter status (SPY 200d MA + BTC 200d MA)."""
    from data.pipeline import download_and_cache
    from data.crypto import download_btc_prices

    result = {}

    try:
        spy_prices = download_and_cache(["SPY"], start="2008-01-01", cache_name="spy_filter").squeeze()
        spy_ma = spy_prices.rolling(200).mean()
        spy_price = float(spy_prices.iloc[-1])
        spy_ma_val = float(spy_ma.iloc[-1])
        result["spy"] = {
            "price": round(spy_price, 2),
            "ma_200": round(spy_ma_val, 2),
            "above_ma": spy_price > spy_ma_val,
            "filter_scalar": 1.0 if spy_price > spy_ma_val else 0.5,
        }
    except Exception:
        result["spy"] = {"error": "Could not load SPY data"}

    try:
        btc_prices = download_btc_prices()
        btc_ma = btc_prices.rolling(200, min_periods=1).mean()
        btc_price = float(btc_prices.iloc[-1])
        btc_ma_val = float(btc_ma.iloc[-1])
        result["btc"] = {
            "price": round(btc_price, 2),
            "ma_200": round(btc_ma_val, 2),
            "above_ma": btc_price > btc_ma_val,
            "filter_scalar": 1.0 if btc_price > btc_ma_val else 0.0,
        }
    except Exception:
        result["btc"] = {"error": "Could not load BTC data"}

    return result
