"""
Alpaca Broker Client — connects to Alpaca paper/live trading.

Wraps the alpaca-trade-api SDK with methods tailored to our strategies:
- Account info and buying power
- Current positions with P&L
- Order submission (market and limit)
- Order history and cancellation

Supports 4 paper trading accounts for multi-factor strategy diversification:
- Account 1: FIRE 0.1 — Momentum (SM + SPY Filter)
- Account 2: FIRE 0.2 — Trend + Low-Vol
- Account 3: FIRE 0.3 — Reversal + Momentum Blend
- Account 4: FIRE 0.4 — Crypto Momentum (daily rebalance)

All methods include error handling and return structured dicts
suitable for our API endpoints.
"""

import os
import re
import logging
from dataclasses import dataclass
from dotenv import load_dotenv
import alpaca_trade_api as tradeapi

log = logging.getLogger("fire.broker")

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Patterns for non-tradeable symbols deposited via corporate actions
# (CVRs, warrants, rights, spinoff stubs). These have no market price
# and cannot be bought or sold through normal order flow.
_NON_TRADEABLE_RE = re.compile(
    r"CVR|WS$|WS[A-Z]$|\.WS|\.RT|WHEN$|\d{3,}[A-Z]{2,}\d{2,}",
    re.IGNORECASE,
)


def is_non_tradeable(symbol: str) -> bool:
    """Detect symbols deposited via corporate actions (CVRs, warrants, etc.).

    These positions appear in Alpaca accounts after mergers/acquisitions
    but have no market data and cannot be traded normally.
    Also catches any position where Alpaca returns None for all pricing fields.
    """
    return bool(_NON_TRADEABLE_RE.search(symbol))


# Account metadata: maps account number to name and default strategy
ACCOUNT_INFO = {
    1: {"name": "FIRE 0.1", "strategy": "sm_filtered", "label": "Momentum"},
    2: {"name": "FIRE 0.2", "strategy": "trend_lowvol", "label": "Trend + Low-Vol"},
    3: {"name": "FIRE 0.3", "strategy": "reversal_blend", "label": "Reversal Blend"},
    4: {"name": "FIRE 0.4", "strategy": "crypto_momentum_filtered", "label": "Crypto"},
}


@dataclass
class OrderRequest:
    """A trade to be executed."""
    symbol: str
    qty: float         # float for crypto fractional quantities
    side: str          # "buy" or "sell"
    order_type: str    # "market" or "limit"
    limit_price: float | None = None
    time_in_force: str = "day"


class AlpacaBroker:
    """Alpaca trading client for paper and live trading.

    Args:
        account: Account number (1, 2, or 3). Selects credentials from .env.
    """

    def __init__(self, account: int = 1):
        if account not in (1, 2, 3, 4):
            raise ValueError(f"Invalid account: {account}. Must be 1, 2, 3, or 4.")

        self.account = account
        self.account_info = ACCOUNT_INFO[account]

        # Account 1 uses base env vars, accounts 2/3 use suffixed vars
        suffix = "" if account == 1 else f"_{account}"
        self.api_key = os.environ.get(f"ALPACA_API_KEY{suffix}", "")
        self.secret_key = os.environ.get(f"ALPACA_SECRET_KEY{suffix}", "")
        self.base_url = os.environ.get(
            "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
        )

        if not self.api_key or not self.secret_key:
            raise ValueError(
                f"ALPACA_API_KEY{suffix} and ALPACA_SECRET_KEY{suffix} must be set in .env"
            )

        self.api = tradeapi.REST(
            key_id=self.api_key,
            secret_key=self.secret_key,
            base_url=self.base_url,
            api_version="v2",
        )

    @property
    def is_paper(self) -> bool:
        return "paper" in self.base_url

    def get_account(self) -> dict:
        """Get account summary: equity, cash, buying power, P&L."""
        acct = self.api.get_account()
        return {
            "account_id": acct.account_number,
            "status": acct.status,
            "equity": float(acct.equity),
            "cash": float(acct.cash),
            "buying_power": float(acct.buying_power),
            "portfolio_value": float(acct.portfolio_value),
            "last_equity": float(acct.last_equity),
            "daily_pnl": float(acct.equity) - float(acct.last_equity),
            "is_paper": self.is_paper,
            "pattern_day_trader": acct.pattern_day_trader,
            "daytrade_count": int(acct.daytrade_count),
            "daytrading_buying_power": float(acct.daytrading_buying_power),
        }

    def get_positions(self) -> list[dict]:
        """Get all open positions with P&L details.

        Positions from corporate actions (CVRs, warrants, etc.) are included
        but flagged with `non_tradeable=True` so callers can filter them.
        """
        positions = self.api.list_positions()
        result = []
        for p in positions:
            avg_entry = float(p.avg_entry_price) if p.avg_entry_price is not None else 0.0
            qty = float(p.qty) if p.qty is not None else 0.0
            current_price = float(p.current_price) if p.current_price is not None else avg_entry
            cost_basis = float(p.cost_basis) if p.cost_basis is not None else avg_entry * qty
            market_value = float(p.market_value) if p.market_value is not None else current_price * qty
            unrealized_pl = float(p.unrealized_pl) if p.unrealized_pl is not None else market_value - cost_basis
            unrealized_plpc = float(p.unrealized_plpc) if p.unrealized_plpc is not None else 0.0
            change_today = float(p.change_today) if p.change_today is not None else 0.0

            # Detect non-tradeable: explicit pattern match OR all pricing fields are None
            all_prices_none = (
                p.market_value is None
                and p.current_price is None
                and p.unrealized_pl is None
            )
            non_tradeable = is_non_tradeable(p.symbol) or all_prices_none
            if non_tradeable:
                log.info(f"Non-tradeable position detected: {p.symbol} (qty={qty})")

            result.append({
                "symbol": p.symbol,
                "qty": qty,
                "side": p.side,
                "market_value": market_value,
                "cost_basis": cost_basis,
                "avg_entry_price": avg_entry,
                "current_price": current_price,
                "unrealized_pl": unrealized_pl,
                "unrealized_plpc": unrealized_plpc,
                "change_today": change_today,
                "non_tradeable": non_tradeable,
            })
        return result

    def get_position_map(self) -> dict[str, float]:
        """Get simple {symbol: qty} map of current tradeable holdings.

        Excludes non-tradeable positions (CVRs, warrants, etc.) so that
        rebalance logic doesn't try to sell them.
        """
        positions = self.api.list_positions()
        result = {}
        for p in positions:
            all_prices_none = (
                p.market_value is None
                and p.current_price is None
                and p.unrealized_pl is None
            )
            if is_non_tradeable(p.symbol) or all_prices_none:
                log.info(f"Excluding non-tradeable from position map: {p.symbol}")
                continue
            result[p.symbol] = float(p.qty)
        return result

    def get_portfolio_value(self) -> float:
        """Get current total portfolio value."""
        acct = self.api.get_account()
        return float(acct.portfolio_value)

    def get_cash(self) -> float:
        """Get available cash."""
        acct = self.api.get_account()
        return float(acct.cash)

    def submit_order(self, order: OrderRequest) -> dict:
        """Submit a single order to Alpaca.

        Returns:
            Dict with order details including order ID and status.
        """
        kwargs = {
            "symbol": order.symbol,
            "qty": order.qty,
            "side": order.side,
            "type": order.order_type,
            "time_in_force": order.time_in_force,
        }
        if order.order_type == "limit" and order.limit_price is not None:
            kwargs["limit_price"] = order.limit_price

        result = self.api.submit_order(**kwargs)
        return {
            "order_id": result.id,
            "symbol": result.symbol,
            "qty": result.qty,
            "side": result.side,
            "type": result.type,
            "status": result.status,
            "submitted_at": str(result.submitted_at),
        }

    def submit_orders(self, orders: list[OrderRequest]) -> list[dict]:
        """Submit multiple orders. Sells execute before buys to free up cash.

        Returns:
            List of order result dicts.
        """
        # Sells first to free up buying power
        sells = [o for o in orders if o.side == "sell"]
        buys = [o for o in orders if o.side == "buy"]

        results = []
        for order in sells + buys:
            try:
                result = self.submit_order(order)
                result["requested_qty"] = order.qty
                results.append(result)
            except Exception as e:
                results.append({
                    "symbol": order.symbol,
                    "side": order.side,
                    "qty": order.qty,
                    "requested_qty": order.qty,
                    "status": "error",
                    "error": str(e),
                })
        return results

    def check_fill_status(self, order_ids: list[str]) -> list[dict]:
        """Check fill status for submitted orders.

        Returns list of order statuses with filled quantities.
        Useful for detecting partial fills after rebalance.
        """
        results = []
        for order_id in order_ids:
            try:
                o = self.api.get_order(order_id)
                results.append({
                    "order_id": o.id,
                    "symbol": o.symbol,
                    "side": o.side,
                    "requested_qty": float(o.qty),
                    "filled_qty": float(o.filled_qty) if o.filled_qty else 0,
                    "status": o.status,
                    "partial_fill": (
                        o.status == "partially_filled"
                        or (o.filled_qty and float(o.filled_qty) < float(o.qty))
                    ),
                    "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else None,
                })
            except Exception as e:
                results.append({
                    "order_id": order_id,
                    "status": "error",
                    "error": str(e),
                })
        return results

    def get_orders(self, status: str = "all", limit: int = 50) -> list[dict]:
        """Get recent orders.

        Args:
            status: "open", "closed", or "all"
            limit: Max number of orders to return
        """
        orders = self.api.list_orders(status=status, limit=limit)
        return [
            {
                "order_id": o.id,
                "symbol": o.symbol,
                "qty": o.qty,
                "filled_qty": o.filled_qty,
                "side": o.side,
                "type": o.type,
                "status": o.status,
                "submitted_at": str(o.submitted_at),
                "filled_at": str(o.filled_at) if o.filled_at else None,
                "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else None,
            }
            for o in orders
        ]

    def cancel_all_orders(self) -> int:
        """Cancel all open orders. Returns number cancelled."""
        cancelled = self.api.cancel_all_orders()
        return len(cancelled) if cancelled else 0

    def get_latest_price(self, symbol: str) -> float:
        """Get latest trade price for a symbol.

        Uses the crypto-specific endpoint for symbols containing '/'
        (e.g. BTC/USD), standard equity endpoint for everything else.
        """
        if "/" in symbol:
            trades = self.api.get_latest_crypto_trades(symbol)
            return float(trades[symbol].price)
        trade = self.api.get_latest_trade(symbol)
        return float(trade.price)

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        """Get latest prices for multiple symbols."""
        prices = {}
        for symbol in symbols:
            try:
                prices[symbol] = self.get_latest_price(symbol)
            except Exception:
                pass  # Skip symbols that fail (delisted, etc.)
        return prices

    def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        clock = self.api.get_clock()
        return clock.is_open
