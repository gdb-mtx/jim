"""Structured rebalance log — appends one JSON line per rebalance event.

Log file: data/rebalance_log.jsonl
Each line is a self-contained JSON object with timestamp, account, strategy,
orders submitted, failures, and filter state.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("fire.rebalance_log")

LOG_FILE = Path(__file__).parent.parent / "data" / "rebalance_log.jsonl"


def log_rebalance(
    account: int,
    strategy_id: str,
    portfolio_value: float,
    orders_submitted: int,
    orders_failed: int,
    order_details: list[dict],
    spy_filter_active: bool = False,
    spy_filter_scalar: float = 1.0,
    btc_filter_active: bool = False,
    btc_filter_scalar: float = 1.0,
    vol_scalar: float = 1.0,
    vol_scalar_diagnostics: dict | None = None,
    raw_signal_weights: dict[str, float] | None = None,
    post_filter_weights: dict[str, float] | None = None,
    execute_error: str | None = None,
    source: str = "manual",
):
    """Append a rebalance event to the JSONL log.

    Args:
        account: Account number (1-4)
        strategy_id: Strategy that was rebalanced
        portfolio_value: Portfolio value at time of rebalance
        orders_submitted: Total orders submitted
        orders_failed: Number of failed orders
        order_details: List of order result dicts
        spy_filter_active: Whether SPY filter reduced exposure
        spy_filter_scalar: SPY filter scalar (1.0 = full, 0.5 = reduced)
        btc_filter_active: Whether BTC filter reduced exposure
        btc_filter_scalar: BTC filter scalar (1.0 = full, 0.0 = cash)
        vol_scalar: Vol-scaling scalar applied to weights (1.0 = no scaling;
            C4 fix 2026-04-21). Only non-trivial for A2/A4 configs with
            `vol_scaling: True`.
        vol_scalar_diagnostics: Diagnostics dict from `compute_live_vol_scalar`
            (realized_vol, n_obs, fallback_reason, etc.). None when the
            vol-scaling gate is skipped.
        raw_signal_weights: Per-symbol weights the strategy produced before
            any overlay (SPY/BTC filter, vol-scaling). Enables post-mortem
            "what did the signal actually say?" without re-running
            generate_signals on a cache that has been overwritten since.
            N4, AUDIT_MONTH2_REVIEW.
        post_filter_weights: Per-symbol weights after SPY/BTC filter, before
            vol-scaling. Multiply by `vol_scalar` to recover the live
            target weights (modulo tradeability pruning). N4.
        execute_error: Exception message if `execute_rebalance` raised mid-
            flight (AUDIT_MONTH2 R4). The `orders` list then reflects
            whatever was recorded before the raise (usually empty if the
            raise was at the Alpaca submit-orders entry point; potentially
            populated for partial failures that escape the per-order guard).
        source: "manual" (API endpoint), "scheduled" (APScheduler), etc.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "account": account,
        "strategy_id": strategy_id,
        "source": source,
        "portfolio_value": round(portfolio_value, 2),
        "orders_submitted": orders_submitted,
        "orders_failed": orders_failed,
        "spy_filter_active": spy_filter_active,
        "spy_filter_scalar": spy_filter_scalar,
        "btc_filter_active": btc_filter_active,
        "btc_filter_scalar": btc_filter_scalar,
        "vol_scalar": vol_scalar,
        "vol_scalar_diagnostics": vol_scalar_diagnostics,
        # Captures intermediate weight stages so post-mortems don't depend on stale price caches (N4).
        "raw_signal_weights": raw_signal_weights,
        "post_filter_weights": post_filter_weights,
        "execute_error": execute_error,
        "orders": [
            {
                "symbol": o.get("symbol", "?"),
                "side": o.get("side", "?"),
                "qty": o.get("qty") or o.get("requested_qty"),
                # Crypto buys submit notional (dollar amount); qty is None until fill.
                "notional": o.get("notional"),
                "status": o.get("status", "unknown"),
                "error": o.get("error"),
            }
            for o in order_details
        ],
    }

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        log.warning(f"Could not write rebalance log: {e}")


def get_recent_rebalances(limit: int = 50, account: int | None = None) -> list[dict]:
    """Read the most recent rebalance events from the log.

    Args:
        limit: Maximum number of entries to return
        account: Optional account filter (1-4). If None, returns all accounts.

    Returns newest-first, up to `limit` entries.
    """
    if not LOG_FILE.exists():
        return []

    entries = []
    try:
        with open(LOG_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if account is not None and entry.get("account") != account:
                            continue
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []

    # Return newest first
    return entries[-limit:][::-1]
