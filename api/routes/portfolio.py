"""Portfolio endpoints — current positions, equity curve, risk metrics."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/summary")
async def portfolio_summary():
    """Get portfolio summary — placeholder until Alpaca is connected."""
    return {
        "total_value": 10000.00,
        "cash": 10000.00,
        "positions": [],
        "daily_pnl": 0.0,
        "total_pnl": 0.0,
        "drawdown": 0.0,
        "status": "paper_trading",
    }
