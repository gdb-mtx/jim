"""Order & rebalance endpoints — preview and execute trades.

Supports 4 paper trading accounts via ?account=1|2|3|4 query param.
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query
from execution.alpaca_broker import AlpacaBroker, ACCOUNT_INFO, active_accounts
from execution.rebalance import compute_rebalance, execute_rebalance, check_price_staleness
from execution.rebalance_log import log_rebalance, get_recent_rebalances
from execution.risk_manager import RiskManager
from execution.validation_gate import ValidationGateError, require_validated
from data.snapshots import take_snapshot
from api.locks import RebalanceLockedError, dual_rebalance_lock

log = logging.getLogger("fire.orders")

router = APIRouter()

# Per-account broker cache (lazy-init)
_brokers: dict[int, AlpacaBroker] = {}
_risk_managers: dict[int, RiskManager] = {}


def _get_broker(account: int) -> AlpacaBroker:
    if account not in _brokers:
        try:
            _brokers[account] = AlpacaBroker(account=account)
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
    return _brokers[account]


def _get_risk_manager(account: int) -> RiskManager:
    if account not in _risk_managers:
        _risk_managers[account] = RiskManager(account=account)
    return _risk_managers[account]


def _require_active(account: int) -> None:
    """Reject requests targeting a retired account before any broker work."""
    status = ACCOUNT_INFO.get(account, {}).get("status", "active")
    if status != "active":
        raise HTTPException(
            status_code=403,
            detail=f"Account {account} status is '{status}' — rebalance not allowed.",
        )


@router.get("/history")
async def order_history(
    account: int = Query(default=1, ge=1, le=4, description="Account number (1-4)"),
    status: str = Query(default="all", description="open, closed, or all"),
    limit: int = Query(default=50, le=200),
):
    """Get recent order history from Alpaca."""
    broker = _get_broker(account)
    return await asyncio.to_thread(broker.get_orders, status=status, limit=limit)


@router.post("/rebalance/preview")
async def preview_rebalance(
    strategy_id: str = Query(description="Strategy or portfolio ID"),
    account: int = Query(default=1, ge=1, le=4, description="Account number (1-4)"),
):
    """Preview a rebalance — compute target positions and orders without executing.

    Returns the full rebalance plan: target weights, position diffs, and orders.
    """
    _require_active(account)
    broker = _get_broker(account)
    risk_mgr = _get_risk_manager(account)

    try:
        result = await asyncio.to_thread(
            compute_rebalance,
            broker=broker,
            strategy_id=strategy_id,
            risk_manager=risk_mgr,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebalance computation failed: {e}")

    return {
        "account": account,
        "strategy_id": result.strategy_id,
        "portfolio_value": result.portfolio_value,
        "target_weights": result.target_weights,
        "target_positions": result.target_positions,
        "current_positions": result.current_positions,
        "orders": [
            {
                "symbol": o.symbol,
                "qty": o.qty,
                "side": o.side,
                "type": o.order_type,
                "current_qty": result.current_positions.get(o.symbol, 0),
                "target_qty": result.target_positions.get(o.symbol, 0),
                "action": (
                    "new" if result.current_positions.get(o.symbol, 0) == 0
                    else "increase" if o.side == "buy"
                    else "exit" if result.target_positions.get(o.symbol, 0) == 0
                    else "decrease"
                ),
            }
            for o in result.orders
        ],
        "num_buys": sum(1 for o in result.orders if o.side == "buy"),
        "num_sells": sum(1 for o in result.orders if o.side == "sell"),
        "risk_check": result.risk_check,
        "spy_filter_active": result.spy_filter_active,
        "spy_filter_scalar": result.spy_filter_scalar,
        "btc_filter_active": result.btc_filter_active,
        "btc_filter_scalar": result.btc_filter_scalar,
        "vol_scalar": result.vol_scalar,
        "vol_scalar_diagnostics": result.vol_scalar_diagnostics,
        "prices": result.prices,
        "missing_prices": result.missing_prices,
        "price_error": result.price_error,
    }


@router.post("/rebalance/execute")
async def execute_rebalance_endpoint(
    strategy_id: str = Query(description="Strategy or portfolio ID"),
    account: int = Query(default=1, ge=1, le=4, description="Account number (1-4)"),
):
    """Execute a rebalance — compute and submit orders to Alpaca.

    WARNING: This submits real orders (paper or live depending on config).
    Always preview first with /rebalance/preview.
    Uses per-account lock to prevent concurrent rebalances.
    """
    _require_active(account)
    try:
        require_validated(account)
    except ValidationGateError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        async with dual_rebalance_lock(account):
            return await _execute_under_lock(account, strategy_id)
    except RebalanceLockedError as e:
        raise HTTPException(status_code=409, detail=str(e))


async def _execute_under_lock(account: int, strategy_id: str):
    """Body of the rebalance endpoint — assumes both locks are held."""
    broker = _get_broker(account)
    risk_mgr = _get_risk_manager(account)

    try:
        result = await asyncio.to_thread(
            compute_rebalance,
            broker=broker,
            strategy_id=strategy_id,
            risk_manager=risk_mgr,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebalance computation failed: {e}")

    # Don't execute with missing prices
    if result.price_error:
        raise HTTPException(
            status_code=422,
            detail=f"Missing prices for: {', '.join(result.missing_prices)}. Cannot execute.",
        )

    # Don't execute if the catastrophe halt (-35% DD) is active.
    # -10% alert is non-blocking and handled by the notification path.
    if result.risk_check.get("halted"):
        raise HTTPException(
            status_code=403,
            detail="Catastrophe halt active (DD <= -35%) — trading halted until manual reset",
        )

    # Price staleness guard — re-fetch and compare
    if result.prices:
        drifted = await asyncio.to_thread(check_price_staleness, broker, result.prices)
        if drifted:
            def _fmt(d: dict) -> str:
                if d.get("reason") == "unfetchable":
                    return f"{d['symbol']} (unfetchable)"
                return f"{d['symbol']} ({d['drift_pct']}%)"
            symbols = ", ".join(_fmt(d) for d in drifted)
            raise HTTPException(
                status_code=409,
                detail=f"Price check failed since computation: {symbols}. Re-preview for current prices.",
            )

    if not result.orders:
        return {
            "message": "No trades needed — portfolio already at target",
            "account": account,
            "strategy_id": strategy_id,
        }

    # Execute — try/finally around the journal so audit trail survives
    # any raise after orders have been submitted to Alpaca (R4).
    order_results: list[dict] = []
    execute_error: str | None = None
    try:
        order_results = await asyncio.to_thread(execute_rebalance, broker, result)
    except Exception as e:
        execute_error = f"{type(e).__name__}: {e}"
    finally:
        failed = [o for o in order_results if o.get("status") == "error"]
        log_rebalance(
            account=account,
            strategy_id=result.strategy_id,
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
            source="manual",
        )

    if execute_error:
        raise HTTPException(
            status_code=500,
            detail=f"Execute failed after journaling state: {execute_error}",
        )

    # Take equity snapshot so dashboard updates immediately.
    # save_snapshot() serializes internally (S3 fix).
    try:
        await asyncio.to_thread(take_snapshot, account)
    except Exception as e:
        log.warning(f"Post-rebalance snapshot failed for account {account}: {e}")

    # Sync filter_state.json so the dashboard banner reflects the decision we
    # just traded against, and so launchd's next filter_check run doesn't
    # compare against a stale "previous" value (which would misdetect or miss
    # flips that happened between launchd runs while the user was manually
    # rebalancing — the travel-window failure mode).
    #
    # Recompute live instead of trusting `result.{spy,btc}_filter_scalar`:
    # PORTFOLIOS["crypto_momentum_filtered"] sets `btc_filter=False` because
    # the filter is internal to CryptoMomentum, which leaves
    # `result.btc_filter_scalar` at the default 1.0 even when BTC is below
    # its 125d MA. Recomputing mirrors `scripts/filter_check.py:compute_filters`.
    try:
        from data import filter_state
        from strategies.portfolio_config import (
            compute_spy_trend_filter,
            compute_btc_trend_filter,
        )

        updates: dict = {}
        track_keys: tuple[str, ...] = ()

        if account in (1, 2):
            live_spy = None
            try:
                live_spy = await asyncio.to_thread(broker.get_latest_price, "SPY")
            except Exception:
                pass
            spy_filter = await asyncio.to_thread(compute_spy_trend_filter, live_price=live_spy)
            updates["spy_scalar"] = float(spy_filter.iloc[-1])
            track_keys = track_keys + ("spy_scalar",)

        if account == 4:
            live_btc = None
            try:
                live_btc = await asyncio.to_thread(broker.get_latest_price, "BTC/USD")
            except Exception:
                pass
            btc_filter = await asyncio.to_thread(compute_btc_trend_filter, live_price=live_btc)
            updates["btc_scalar"] = float(btc_filter.iloc[-1])
            track_keys = track_keys + ("btc_scalar",)

        if updates:
            await asyncio.to_thread(
                filter_state.update_fields,
                updates,
                track_flips=track_keys,
            )
    except Exception as e:
        log.warning(f"Post-rebalance filter_state sync failed for account {account} (non-fatal): {e}")

    return {
        "account": account,
        "strategy_id": result.strategy_id,
        "portfolio_value": result.portfolio_value,
        "orders_submitted": len(order_results),
        "orders_failed": len(failed),
        "orders": order_results,
        "spy_filter_active": result.spy_filter_active,
        "spy_filter_scalar": result.spy_filter_scalar,
        "btc_filter_active": result.btc_filter_active,
        "btc_filter_scalar": result.btc_filter_scalar,
    }


@router.get("/rebalance/history")
async def rebalance_history(
    limit: int = Query(default=50, le=200),
    account: int | None = Query(default=None, ge=1, le=4, description="Filter by account (optional)"),
):
    """Get recent rebalance events from the structured log."""
    return await asyncio.to_thread(get_recent_rebalances, limit=limit, account=account)


@router.post("/cancel-all")
async def cancel_all_orders(
    account: int = Query(default=1, ge=1, le=4, description="Account number (1-4)"),
):
    """Cancel all open orders."""
    broker = _get_broker(account)
    return {"account": account, "cancelled": await asyncio.to_thread(broker.cancel_all_orders)}
