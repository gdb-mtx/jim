"""Live volatility scaling — mirrors `apply_vol_scaling` for the rebalance path.

The backtest scales a returns series after-the-fact; live trading needs today's
scalar to multiply strategy weights before sizing orders. Math is identical
(EWMA realized vol, target/realized, clipped), but in live we compute at T from
equity through T-1, so the backtest's `.shift(1)` lag is implicit in our data
slice and not applied explicitly.

Resolves AUDIT_MONTH2 C4 — vol-scaling was in the backtest for A2 + A4 but not
in live. Backtest cap 1.5 was also unreachable since Alpaca paper is spot-only /
no margin; cap=1.0 here enforces sim/live parity on the upside.
"""

import logging
import math

from data.snapshots import load_snapshots

log = logging.getLogger("fire.vol_scaling")


def compute_live_vol_scalar(
    account_id: int,
    vol_target: float = 0.15,
    vol_halflife: int = 21,
    scalar_floor: float = 0.5,
    scalar_cap: float = 1.0,
    min_history_days: int = 21,
) -> tuple[float, dict]:
    """Today's live vol scalar from per-account snapshot equity.

    Returns (scalar, diagnostics). Falls back to 1.0 with a logged reason when
    there isn't enough clean equity history to compute a trustworthy EWMA —
    covers cold-start (A4 has been all-cash since launch, no signal-trading
    returns) and the data-bug window (equity rows are clean per AUDIT; cash /
    positions_count had NaNs but we don't read those here).
    """
    df = load_snapshots(account_id)
    equity = df["equity"].dropna() if not df.empty else None

    diagnostics: dict = {
        "account_id": account_id,
        "vol_target": vol_target,
        "vol_halflife": vol_halflife,
        "scalar_floor": scalar_floor,
        "scalar_cap": scalar_cap,
    }

    if equity is None or len(equity) < min_history_days + 1:
        diagnostics["fallback_reason"] = "cold_start"
        diagnostics["n_obs"] = 0 if equity is None else int(len(equity))
        log.info(
            f"vol_scalar account={account_id} cold_start n_obs={diagnostics['n_obs']} "
            f"< min_history_days+1={min_history_days + 1} → scalar=1.0"
        )
        return 1.0, diagnostics

    returns = equity.pct_change().dropna()
    if len(returns) < min_history_days:
        diagnostics["fallback_reason"] = "cold_start"
        diagnostics["n_obs"] = int(len(returns))
        return 1.0, diagnostics

    ewma_var = returns.ewm(halflife=vol_halflife).var()
    latest_var = float(ewma_var.iloc[-1])

    if latest_var <= 0 or math.isnan(latest_var):
        diagnostics["fallback_reason"] = "zero_variance"
        diagnostics["n_obs"] = int(len(returns))
        log.warning(
            f"vol_scalar account={account_id} zero/NaN variance → scalar=1.0"
        )
        return 1.0, diagnostics

    realized_vol = math.sqrt(latest_var) * math.sqrt(252)
    raw_scalar = vol_target / realized_vol
    scalar = max(scalar_floor, min(scalar_cap, raw_scalar))

    diagnostics["n_obs"] = int(len(returns))
    diagnostics["realized_vol"] = round(realized_vol, 6)
    diagnostics["raw_scalar"] = round(raw_scalar, 6)
    diagnostics["scalar"] = round(scalar, 6)

    return scalar, diagnostics
