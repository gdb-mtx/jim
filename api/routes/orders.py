"""Order & rebalance endpoints — preview and execute trades.

Supports 3 paper trading accounts via ?account=1|2|3 query param.
"""

from fastapi import APIRouter, HTTPException, Query
from execution.alpaca_broker import AlpacaBroker, ACCOUNT_INFO
from execution.rebalance import compute_rebalance, execute_rebalance
from execution.risk_manager import RiskManager

router = APIRouter()

# Per-account broker cache (lazy-init)
_brokers: dict[int, AlpacaBroker] = {}
_risk_manager = RiskManager()


def _get_broker(account: int) -> AlpacaBroker:
    if account not in _brokers:
        try:
            _brokers[account] = AlpacaBroker(account=account)
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
    return _brokers[account]


@router.get("/history")
async def order_history(
    account: int = Query(default=1, ge=1, le=3, description="Account number (1-3)"),
    status: str = Query(default="all", description="open, closed, or all"),
    limit: int = Query(default=50, le=200),
):
    """Get recent order history from Alpaca."""
    broker = _get_broker(account)
    return broker.get_orders(status=status, limit=limit)


@router.post("/rebalance/preview")
async def preview_rebalance(
    strategy_id: str = Query(description="Strategy or portfolio ID"),
    account: int = Query(default=1, ge=1, le=3, description="Account number (1-3)"),
):
    """Preview a rebalance — compute target positions and orders without executing.

    Returns the full rebalance plan: target weights, position diffs, and orders.
    """
    broker = _get_broker(account)

    try:
        result = compute_rebalance(
            broker=broker,
            strategy_id=strategy_id,
            risk_manager=_risk_manager,
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
            }
            for o in result.orders
        ],
        "num_buys": sum(1 for o in result.orders if o.side == "buy"),
        "num_sells": sum(1 for o in result.orders if o.side == "sell"),
        "risk_check": result.risk_check,
        "spy_filter_active": result.spy_filter_active,
        "spy_filter_scalar": result.spy_filter_scalar,
    }


@router.post("/rebalance/execute")
async def execute_rebalance_endpoint(
    strategy_id: str = Query(description="Strategy or portfolio ID"),
    account: int = Query(default=1, ge=1, le=3, description="Account number (1-3)"),
):
    """Execute a rebalance — compute and submit orders to Alpaca.

    WARNING: This submits real orders (paper or live depending on config).
    Always preview first with /rebalance/preview.
    """
    broker = _get_broker(account)

    try:
        result = compute_rebalance(
            broker=broker,
            strategy_id=strategy_id,
            risk_manager=_risk_manager,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebalance computation failed: {e}")

    # Don't execute if circuit breaker tripped
    if result.risk_check.get("portfolio_halted"):
        raise HTTPException(
            status_code=403,
            detail="Portfolio circuit breaker active — trading halted",
        )

    if not result.orders:
        return {
            "message": "No trades needed — portfolio already at target",
            "account": account,
            "strategy_id": strategy_id,
        }

    # Execute
    order_results = execute_rebalance(broker, result)

    return {
        "account": account,
        "strategy_id": result.strategy_id,
        "portfolio_value": result.portfolio_value,
        "orders_submitted": len(order_results),
        "orders": order_results,
        "spy_filter_active": result.spy_filter_active,
        "spy_filter_scalar": result.spy_filter_scalar,
    }


@router.post("/cancel-all")
async def cancel_all_orders(
    account: int = Query(default=1, ge=1, le=3, description="Account number (1-3)"),
):
    """Cancel all open orders."""
    broker = _get_broker(account)
    count = broker.cancel_all_orders()
    return {"account": account, "cancelled": count}
