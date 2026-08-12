"""Live volatility scaling.

Two estimators:

- `compute_signal_vol_scalar` (default since 2026-08-12): runs the signal
  book through `run_portfolio` and reads the scalar the backtest itself
  would apply next — semantic parity by construction. The 08-11 diagnostic
  found the account-equity estimator diverging 1.08 vs 0.82 from three
  causes it can't avoid: compositional lag (the account's equity history
  reflects last cycle's holdings, not the current signal basket), a
  leverage feedback loop (it measures the scaled book; backtest measures
  raw), and weekend snapshot rows diluting vol.

- `compute_live_vol_scalar` (legacy, account-equity based): kept for
  diagnostics and as a cross-check, not used for sizing.
"""

import logging
import math

from data.snapshots import load_snapshots

log = logging.getLogger("fire.vol_scaling")


def compute_signal_vol_scalar(
    portfolio_id: str,
    vol_target: float = 0.15,
    vol_halflife: int = 21,
    scalar_floor: float = 0.5,
    scalar_cap: float = 1.0,
    lookback_start: str = "2023-01-01",
) -> tuple[float, dict]:
    """Tomorrow's vol scalar computed exactly as the backtest computes it.

    Runs the signal book (settled bars through yesterday, from the shared
    caches) and derives the scalar from the raw pre-scaling return series —
    the same series `apply_vol_scaling` uses in validation. The explicit
    params override the portfolio config's so the caller (rebalance.py)
    stays the single source for crypto clamping / cap decisions.

    Research surface import is deliberate: reusing `run_portfolio` is the
    parity guarantee. A parallel "live" reimplementation is exactly the
    divergence class this replaces.
    """
    diagnostics: dict = {
        "portfolio_id": portfolio_id,
        "vol_target": vol_target,
        "vol_halflife": vol_halflife,
        "scalar_floor": scalar_floor,
        "scalar_cap": scalar_cap,
        "estimator": "signal_book",
    }
    from strategies.portfolio_backtest import run_portfolio

    stages: dict = {}
    run_portfolio(portfolio_id, start=lookback_start, stages_out=stages)
    raw = stages.get("raw_returns")
    if raw is None or len(raw) < vol_halflife + 1:
        diagnostics["fallback_reason"] = "insufficient_signal_history"
        diagnostics["n_obs"] = 0 if raw is None else int(len(raw))
        log.warning(
            f"signal_vol_scalar portfolio={portfolio_id} insufficient history → scalar=1.0"
        )
        return 1.0, diagnostics

    ewma_var = raw.ewm(halflife=vol_halflife).var()
    latest_var = float(ewma_var.iloc[-1])
    if latest_var <= 0 or math.isnan(latest_var):
        diagnostics["fallback_reason"] = "zero_variance"
        diagnostics["n_obs"] = int(len(raw))
        return 1.0, diagnostics

    realized_vol = math.sqrt(latest_var) * math.sqrt(252)
    raw_scalar = vol_target / realized_vol
    scalar = max(scalar_floor, min(scalar_cap, raw_scalar))

    diagnostics["n_obs"] = int(len(raw))
    diagnostics["last_signal_bar"] = str(raw.index[-1].date())
    diagnostics["realized_vol"] = round(realized_vol, 6)
    diagnostics["raw_scalar"] = round(raw_scalar, 6)
    diagnostics["scalar"] = round(scalar, 6)
    return scalar, diagnostics


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
