"""Portfolio endpoints — live account data from Alpaca.

Supports 3 paper trading accounts via ?account=1|2|3 query param.
"""

from fastapi import APIRouter, HTTPException, Query
from execution.alpaca_broker import AlpacaBroker, ACCOUNT_INFO

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
    account: int = Query(default=1, ge=1, le=3, description="Account number (1-3)"),
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
    account: int = Query(default=1, ge=1, le=3, description="Account number (1-3)"),
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
    account: int = Query(default=1, ge=1, le=3, description="Account number (1-3)"),
):
    """Get just the portfolio value (lightweight)."""
    broker = _get_broker(account)
    return {"portfolio_value": broker.get_portfolio_value()}
