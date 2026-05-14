"""Per-ticker value-plausibility checks for cached market data."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger("fire.plausibility")

STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "risk_state" / "plausibility_state.json"


# Bands anchor to historical facts. Don't loosen them to make a failure go away —
# tight floors are part of the cross-contamination guard (a stock series under
# the BTC ticker would trip the BTC floor immediately).
BANDS: dict[str, tuple[float, float, str]] = {
    "BTC-USD": (1000.0, 500_000.0, "BTC has not closed below $1k since Dec 2017"),
    "ETH-USD": (50.0, 20_000.0, "ETH has not closed below $80 since Feb 2018"),
    "SPY": (40.0, 2_000.0, "SPY auto-adjusted low was $49.81 on 2009-03-09"),
    "^VIX": (5.0, 100.0, "VIX historical range ~9 to ~85 (Oct 2008 / Mar 2020)"),
    "SHY": (40.0, 100.0, "SHY adjusted-close goes to ~$54 in 2005 due to dividend adjustments"),
}


class PlausibilityError(RuntimeError):
    """Cached-data candidate failed plausibility — do NOT write to cache."""


def assert_plausible(series: pd.Series, ticker: str) -> None:
    """Raise `PlausibilityError` if series values are implausible for ticker. Unknown tickers pass silently."""
    if ticker not in BANDS:
        return

    min_val, max_val, reason = BANDS[ticker]

    clean = series.dropna()
    if len(clean) == 0:
        _record_success(ticker, n_obs=0)
        return

    obs_max = float(clean.max())
    obs_min = float(clean.min())

    if obs_min < min_val or obs_max > max_val:
        reason_msg = (
            f"Plausibility FAIL for {ticker}: observed range "
            f"[{obs_min:.4f}, {obs_max:.4f}] escapes band [{min_val}, {max_val}] "
            f"over {len(clean)} rows. Reason band: {reason}. "
            f"Refusing to cache — likely wrong-ticker data from source."
        )
        _record_failure(ticker, reason_msg, obs_min=obs_min, obs_max=obs_max, n_obs=len(clean))
        raise PlausibilityError(reason_msg)

    # Success
    _record_success(ticker, n_obs=len(clean))


def assert_plausible_df(df: pd.DataFrame) -> None:
    """Apply `assert_plausible` to each column. Raises on first failure."""
    if df is None or df.empty:
        return
    for col in df.columns:
        assert_plausible(df[col], str(col))


@dataclass
class DivergenceResult:
    ticker: str
    within_threshold: bool
    cached_value: float
    live_value: float
    divergence_pct: float
    threshold_pct: float


def cross_validate_last_close(
    series: pd.Series,
    ticker: str,
    live_price: float,
    threshold_pct: float = 0.05,
) -> DivergenceResult:
    """Compare cached last-close to live price. Records divergences; does NOT raise."""
    clean = series.dropna()
    if len(clean) == 0:
        return DivergenceResult(
            ticker=ticker,
            within_threshold=True,
            cached_value=float("nan"),
            live_value=live_price,
            divergence_pct=0.0,
            threshold_pct=threshold_pct,
        )

    cached = float(clean.iloc[-1])
    if cached <= 0 or live_price <= 0:
        return DivergenceResult(
            ticker=ticker,
            within_threshold=False,
            cached_value=cached,
            live_value=live_price,
            divergence_pct=float("inf"),
            threshold_pct=threshold_pct,
        )

    divergence = abs(cached - live_price) / cached
    within = divergence <= threshold_pct

    if not within:
        _record_divergence(
            ticker=ticker,
            cached_value=cached,
            live_value=live_price,
            divergence_pct=divergence,
            threshold_pct=threshold_pct,
        )

    return DivergenceResult(
        ticker=ticker,
        within_threshold=within,
        cached_value=cached,
        live_value=live_price,
        divergence_pct=divergence,
        threshold_pct=threshold_pct,
    )


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception as e:
        log.warning(f"plausibility_state.json unreadable: {e}; treating as empty")
        return {}


def _write_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(STATE_PATH.parent), prefix=".plausibility_", suffix=".json.tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(state, f, indent=2, sort_keys=True)
        os.replace(tmp_path, STATE_PATH)
    except Exception as e:
        # Callers run inside exception-suppressing paths; explicit log keeps the dashboard banner accurate.
        log.error(f"Failed to persist plausibility state to {STATE_PATH}: {e}")
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_failure(
    ticker: str,
    reason: str,
    obs_min: float,
    obs_max: float,
    n_obs: int,
) -> None:
    state = _load_state()
    entry = state.get(ticker, {})
    entry.update({
        "last_failure_at": _now_iso(),
        "last_failure_reason": reason,
        "last_failure_obs_min": obs_min,
        "last_failure_obs_max": obs_max,
        "last_failure_n_obs": n_obs,
    })
    state[ticker] = entry
    _write_state(state)
    log.error(f"[plausibility] {reason}")


def _record_success(ticker: str, n_obs: int) -> None:
    state = _load_state()
    entry = state.get(ticker, {})
    entry.update({
        "last_success_at": _now_iso(),
        "last_success_n_obs": n_obs,
    })
    state[ticker] = entry
    _write_state(state)


def _record_divergence(
    ticker: str,
    cached_value: float,
    live_value: float,
    divergence_pct: float,
    threshold_pct: float,
) -> None:
    state = _load_state()
    entry = state.get(ticker, {})
    entry.update({
        "last_divergence_at": _now_iso(),
        "last_divergence_cached": cached_value,
        "last_divergence_live": live_value,
        "last_divergence_pct": divergence_pct,
        "last_divergence_threshold_pct": threshold_pct,
    })
    state[ticker] = entry
    _write_state(state)
    log.warning(
        f"[plausibility] {ticker} cached {cached_value:.4f} diverges "
        f"{divergence_pct:.2%} from live {live_value:.4f} (threshold {threshold_pct:.2%})"
    )


def get_state() -> dict:
    """Return the current plausibility state dict. Used by the API endpoint."""
    return _load_state()


def has_active_issues(state: dict | None = None, divergence_ttl_hours: int = 24) -> list[dict]:
    """Return the list of tickers with active plausibility issues.

    "Active" means either:
      - last_failure_at > last_success_at (write-time failure unresolved), OR
      - last_divergence_at within the last `divergence_ttl_hours` hours.

    Dashboard uses this to decide whether to show the warning banner.
    """
    if state is None:
        state = _load_state()
    active: list[dict] = []
    now = datetime.now(timezone.utc)
    for ticker, entry in state.items():
        failure_at = entry.get("last_failure_at")
        success_at = entry.get("last_success_at")
        divergence_at = entry.get("last_divergence_at")

        unresolved_failure = False
        if failure_at:
            if not success_at:
                unresolved_failure = True
            else:
                unresolved_failure = _parse_iso(failure_at) > _parse_iso(success_at)

        recent_divergence = False
        if divergence_at:
            age_hours = (now - _parse_iso(divergence_at)).total_seconds() / 3600
            recent_divergence = age_hours <= divergence_ttl_hours

        if unresolved_failure or recent_divergence:
            active.append({
                "ticker": ticker,
                "unresolved_failure": unresolved_failure,
                "recent_divergence": recent_divergence,
                **entry,
            })
    return active


def _parse_iso(s: str) -> datetime:
    # datetime.fromisoformat handles "+00:00" suffix in 3.11+
    return datetime.fromisoformat(s)
