"""Order & rebalance endpoints — preview and execute trades."""

from fastapi import APIRouter, HTTPException, Query
from execution.alpaca_broker import AlpacaBroker
from execution.rebalance import compute_rebalance, execute_rebalance
from execution.risk_manager import RiskManager

router = APIRouter()

_broker: AlpacaBroker | None = None
_risk_manager = RiskManager()


def _get_broker() -> AlpacaBroker:
    global _broker
    if _broker is None:
        try:
            _broker = AlpacaBroker()
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
    return _broker


@router.get("/history")
async def order_history(
    status: str = Query(default="all", description="open, closed, or all"),
    limit: int = Query(default=50, le=200),
):
    """Get recent order history from Alpaca."""
    broker = _get_broker()
    return broker.get_orders(status=status, limit=limit)


@router.post("/rebalance/preview")
async def preview_rebalance(
    strategy_id: str = Query(description="Strategy or portfolio ID"),
):
    """Preview a rebalance — compute target positions and orders without executing.

    Returns the full rebalance plan: target weights, position diffs, and orders.
    """
    broker = _get_broker()

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
):
    """Execute a rebalance — compute and submit orders to Alpaca.

    WARNING: This submits real orders (paper or live depending on config).
    Always preview first with /rebalance/preview.
    """
    broker = _get_broker()

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
            "strategy_id": strategy_id,
        }

    # Execute
    order_results = execute_rebalance(broker, result)

    return {
        "strategy_id": result.strategy_id,
        "portfolio_value": result.portfolio_value,
        "orders_submitted": len(order_results),
        "orders": order_results,
        "spy_filter_active": result.spy_filter_active,
        "spy_filter_scalar": result.spy_filter_scalar,
    }


@router.post("/cancel-all")
async def cancel_all_orders():
    """Cancel all open orders."""
    broker = _get_broker()
    count = broker.cancel_all_orders()
    return {"cancelled": count}
