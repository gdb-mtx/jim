"""Portfolio endpoints — live account data from Alpaca."""

from fastapi import APIRouter, HTTPException
from execution.alpaca_broker import AlpacaBroker

router = APIRouter()

# Lazy-init broker (only connects when first endpoint is hit)
_broker: AlpacaBroker | None = None


def _get_broker() -> AlpacaBroker:
    global _broker
    if _broker is None:
        try:
            _broker = AlpacaBroker()
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
    return _broker


@router.get("/summary")
async def portfolio_summary():
    """Get account summary — equity, cash, P&L, positions count."""
    broker = _get_broker()
    account = broker.get_account()
    positions = broker.get_positions()

    total_unrealized_pl = sum(p["unrealized_pl"] for p in positions)

    return {
        **account,
        "positions_count": len(positions),
        "total_unrealized_pl": total_unrealized_pl,
        "market_open": broker.is_market_open(),
    }


@router.get("/positions")
async def portfolio_positions():
    """Get all open positions with P&L details."""
    broker = _get_broker()
    return broker.get_positions()


@router.get("/value")
async def portfolio_value():
    """Get just the portfolio value (lightweight)."""
    broker = _get_broker()
    return {"portfolio_value": broker.get_portfolio_value()}
