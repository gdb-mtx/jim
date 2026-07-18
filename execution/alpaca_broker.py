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
import time
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
    """Detect symbols deposited via corporate actions (CVRs, warrants, etc.)."""
    return bool(_NON_TRADEABLE_RE.search(symbol))


def _is_position_non_tradeable(position) -> bool:
    """Check symbol pattern AND whether Alpaca returned pricing data."""
    all_prices_none = (
        position.market_value is None
        and position.current_price is None
        and position.unrealized_pl is None
    )
    return is_non_tradeable(position.symbol) or all_prices_none


# Account metadata: maps account number to name, strategy, and live status.
# `status="retired"` + `strategy=None` preserves the Alpaca account slot for
# future strategy assignment without trading activity. Liquidation is a
# prerequisite (see scripts/liquidate_account.py).
ACCOUNT_INFO = {
    1: {"name": "FIRE 0.1", "strategy": "sm_filtered", "label": "Momentum", "status": "active"},
    2: {"name": "FIRE 0.2", "strategy": "trend_lowvol", "label": "Trend + Low-Vol", "status": "active"},
    3: {"name": "FIRE 0.3", "strategy": None, "label": "Retired — tail-leg pilot host", "status": "retired", "retired_at": "2026-04-20"},
    4: {"name": "FIRE 0.4", "strategy": None, "label": "Retired (was Crypto)", "status": "retired", "retired_at": "2026-07-13"},
}


def active_accounts() -> list[int]:
    """Account numbers with status='active'. Use for iterations that drive
    live trading, snapshots, and dashboard live views. Historical endpoints
    and backtests should still iterate the full ACCOUNT_INFO."""
    return [n for n, info in ACCOUNT_INFO.items() if info.get("status", "active") == "active"]


@dataclass
class OrderRequest:
    """A trade to be executed.

    For crypto market BUYS, prefer `notional` over `qty` to eliminate
    price-drift-between-preview-and-fill rejects. Alpaca figures out the
    qty at fill price, so we spend exactly the dollar amount we have.
    `qty` is always populated for logging/display; `notional`, when set,
    takes precedence at submission.
    """
    symbol: str
    qty: float         # float for crypto fractional quantities
    side: str          # "buy" or "sell"
    order_type: str    # "market" or "limit"
    limit_price: float | None = None
    time_in_force: str = "day"
    notional: float | None = None


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
            "pattern_day_trader": getattr(acct, "pattern_day_trader", False),
            "daytrade_count": int(getattr(acct, "daytrade_count", 0)),
            "daytrading_buying_power": float(getattr(acct, "daytrading_buying_power", 0)),
        }

    def get_positions(self) -> list[dict]:
        """Get all open positions with P&L details.

        Positions from corporate actions (CVRs, warrants, etc.) are included
        but flagged with `non_tradeable=True` so callers can filter them.

        Crypto position symbols are normalized from Alpaca's position-API
        form (`BTCUSD`) to the order-API form (`BTC/USD`) so internal code
        can use a single representation everywhere.
        """
        from data.crypto import normalize_alpaca_position_symbol
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

            non_tradeable = _is_position_non_tradeable(p)
            if non_tradeable:
                log.info(f"Non-tradeable position detected: {p.symbol} (qty={qty})")

            result.append({
                "symbol": normalize_alpaca_position_symbol(p.symbol),
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
        rebalance logic doesn't try to sell them. Crypto symbols are
        normalized to the slashed order-API form (`BTC/USD`), matching
        target-weight keys.
        """
        from data.crypto import normalize_alpaca_position_symbol
        positions = self.api.list_positions()
        result = {}
        for p in positions:
            if _is_position_non_tradeable(p):
                log.info(f"Excluding non-tradeable from position map: {p.symbol}")
                continue
            result[normalize_alpaca_position_symbol(p.symbol)] = float(p.qty)
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
            "side": order.side,
            "type": order.order_type,
            "time_in_force": order.time_in_force,
        }
        # Notional ($-amount) for crypto market buys — Alpaca computes qty
        # at fill price, sidestepping the price-drift reject path. Alpaca
        # expects one of qty / notional, not both.
        if order.notional is not None:
            kwargs["notional"] = order.notional
        else:
            kwargs["qty"] = order.qty
        if order.order_type == "limit" and order.limit_price is not None:
            kwargs["limit_price"] = order.limit_price

        result = self.api.submit_order(**kwargs)
        return {
            "order_id": result.id,
            "symbol": result.symbol,
            "qty": result.qty,
            "notional": order.notional,
            "side": result.side,
            "type": result.type,
            "status": result.status,
            "submitted_at": str(result.submitted_at),
        }

    def _verify_sell_qtys(
        self,
        orders: list[OrderRequest],
        tolerance: float = 0.01,
    ) -> tuple[list[OrderRequest], list[dict]]:
        """Pre-submit guard: block sells whose qty exceeds broker-current.

        Re-queries positions right before submission. Sells more than
        `tolerance` (1%) above broker-current qty are blocked — prevents
        silent leverage from stale position reads. Returns
        `(safe_orders, blocked_results)`. Fail-open: if position fetch
        fails, proceeds with a warning.
        """
        sells = [o for o in orders if o.side == "sell"]
        if not sells:
            return list(orders), []

        try:
            current = self.get_position_map()
        except Exception as e:
            log.warning(
                f"Pre-submit guard: position fetch failed ({e}); "
                f"proceeding without sell-qty verification"
            )
            return list(orders), []

        safe: list[OrderRequest] = []
        blocked: list[dict] = []
        for o in orders:
            if o.side != "sell":
                safe.append(o)
                continue
            cur_qty = current.get(o.symbol, 0.0)
            max_allowed = cur_qty * (1 + tolerance)
            if o.qty > max_allowed and o.qty > 0:
                pct = ((o.qty - cur_qty) / cur_qty * 100) if cur_qty > 0 else float("inf")
                log.error(
                    f"Pre-submit guard BLOCKED sell {o.symbol}: requested "
                    f"qty={o.qty} > broker-current {cur_qty} "
                    f"(over by {pct:.1f}%, tolerance {tolerance*100:.0f}%). "
                    f"Likely stale position data from compute_rebalance. "
                    f"Skipping order to prevent over-sell."
                )
                blocked.append({
                    "symbol": o.symbol,
                    "side": "sell",
                    "qty": o.qty,
                    "notional": o.notional,
                    "requested_qty": o.qty,
                    "status": "error",
                    "error": (
                        f"pre-submit guard: sell qty {o.qty} exceeds broker "
                        f"current {cur_qty} (over by {pct:.1f}%)"
                    ),
                })
            else:
                safe.append(o)
        return safe, blocked

    def _submit_order_batch(self, orders: list[OrderRequest]) -> list[dict]:
        """Submit a list of orders, returning result dicts (sells before buys)."""
        results = []
        for order in orders:
            try:
                result = self.submit_order(order)
                result["requested_qty"] = order.qty
                results.append(result)
            except Exception as e:
                results.append({
                    "symbol": order.symbol,
                    "side": order.side,
                    "qty": order.qty,
                    "notional": order.notional,
                    "requested_qty": order.qty,
                    "status": "error",
                    "error": str(e),
                })
        return results

    def submit_orders(self, orders: list[OrderRequest]) -> list[dict]:
        """Submit multiple orders. Sells execute before buys to free up cash.

        For crypto batches with sells AND buys, prefer
        `submit_orders_settled` — crypto pending sells don't credit
        `non_marginable_buying_power` until filled.
        """
        safe, blocked = self._verify_sell_qtys(orders)
        sells = [o for o in safe if o.side == "sell"]
        buys = [o for o in safe if o.side == "buy"]
        return list(blocked) + self._submit_order_batch(sells + buys)

    def submit_orders_settled(
        self,
        orders: list[OrderRequest],
        sell_settle_timeout: float = 60.0,
        poll_interval: float = 2.0,
    ) -> list[dict]:
        """Submit sells, wait for fills, rescale buys against measured cash, submit buys.

        Crypto sells don't credit `non_marginable_buying_power` until
        filled. This method measures post-sell cash instead of predicting
        it, so partial fills and rejections shrink buys automatically.

        Falls through to `submit_orders` for equity-only or sell-only
        batches. Crypto sells+buys: submit sells → poll fills →
        re-read cash → rescale buy notionals → submit buys.
        """
        safe, blocked = self._verify_sell_qtys(orders)

        sells = [o for o in safe if o.side == "sell"]
        buys = [o for o in safe if o.side == "buy"]
        has_crypto = any("/" in o.symbol for o in safe)

        # Fast path: equity (margin credits proceeds immediately) or no sell+buy mix.
        if not sells or not buys or not has_crypto:
            return list(blocked) + self._submit_order_batch(sells + buys)

        # --- Submit sells ---
        sell_results = self._submit_order_batch(sells)
        sell_order_ids = [r["order_id"] for r in sell_results if r.get("order_id")]

        # --- Wait for sells to settle ---
        terminal = {"filled", "rejected", "canceled", "expired"}
        if sell_order_ids:
            deadline = time.monotonic() + sell_settle_timeout
            settled = False
            while time.monotonic() < deadline:
                statuses = self.check_fill_status(sell_order_ids)
                if all(s.get("status") in terminal for s in statuses):
                    settled = True
                    break
                time.sleep(poll_interval)
            if not settled:
                log.warning(
                    f"Sell settlement timeout after {sell_settle_timeout}s — "
                    f"proceeding with whatever cash is available."
                )

        # Rescale buys against actual post-sell cash.
        actual_cash = self.get_cash()
        total_buy_notional = sum((o.notional or 0.0) for o in buys)
        if total_buy_notional > 0:
            cash_budget = actual_cash * 0.999
            shortfall = total_buy_notional - cash_budget
            if shortfall > 1.0:
                scale = cash_budget / total_buy_notional
                log.warning(
                    f"Crypto buy notional ${total_buy_notional:.2f} exceeds actual "
                    f"post-sell cash budget ${cash_budget:.2f} by ${shortfall:.2f}. "
                    f"Scaling by {scale:.4f}."
                )
                for o in buys:
                    if o.notional is not None:
                        o.notional = round(o.notional * scale, 2)

        # Filter dust before submitting.
        dust_results: list[dict] = []
        valid_buys: list[OrderRequest] = []
        for o in buys:
            if o.notional is not None and o.notional < 1.0:
                dust_results.append({
                    "symbol": o.symbol,
                    "side": o.side,
                    "qty": o.qty,
                    "notional": o.notional,
                    "requested_qty": o.qty,
                    "status": "skipped",
                    "error": f"notional ${o.notional:.2f} below $1 minimum after rescale",
                })
            else:
                valid_buys.append(o)

        return list(blocked) + sell_results + dust_results + self._submit_order_batch(valid_buys)

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

    def close_all_positions(self, cancel_open_orders: bool = True) -> list[dict]:
        """Close every position on this account via market orders.

        Used for account retirement / full liquidation. Alpaca returns a
        response object per symbol with the resulting order. Caller is
        responsible for logging to the rebalance journal if desired.

        Note: the alpaca-trade-api `close_all_positions()` doesn't accept
        a cancel-orders kwarg on this SDK version, so we cancel open
        orders separately before calling this when needed.
        """
        if cancel_open_orders:
            self.cancel_all_orders()
        responses = self.api.close_all_positions()
        results = []
        for r in responses or []:
            # alpaca-trade-api wraps each close in a response with .body (the order) and .status
            body = getattr(r, "body", None) or r
            status_code = getattr(r, "status", None)
            results.append({
                "symbol": getattr(body, "symbol", None),
                "order_id": getattr(body, "id", None),
                "qty": getattr(body, "qty", None),
                "side": getattr(body, "side", None),
                "status": getattr(body, "status", None),
                "http_status": status_code,
            })
        return results

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
        """Get latest prices for multiple symbols.

        Skips untradeable assets (delisted, acquired, inactive) so the
        rebalance code won't generate orders for them.
        """
        prices = {}
        for symbol in symbols:
            try:
                prices[symbol] = self.get_latest_price(symbol)
            except Exception as e:
                log.debug(f"Skipping {symbol} in price fetch: {e}")
        return prices

    def check_tradeable(self, symbols: list[str]) -> set[str]:
        """Return the subset of symbols that are tradeable on Alpaca.

        Used to filter out delisted/acquired assets before generating orders.
        """
        untradeable = set()
        for symbol in symbols:
            try:
                asset = self.api.get_asset(symbol)
                if not asset.tradable:
                    log.warning(f"Untradeable asset: {symbol} (status={asset.status})")
                    untradeable.add(symbol)
            except Exception as e:
                log.debug(f"Treating {symbol} as untradeable (API error: {e})")
                untradeable.add(symbol)
        return set(symbols) - untradeable

    def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        clock = self.api.get_clock()
        return clock.is_open
