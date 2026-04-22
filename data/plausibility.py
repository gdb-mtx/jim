"""Per-ticker value-plausibility checks for cached market data.

Guards against the "yfinance returned wrong data under the right ticker"
failure mode — AUDIT_MONTH2 S5, session 4. On 2026-04-21, yfinance returned
a plausibly-shaped DataFrame under "BTC-USD" whose values were clearly not
BTC (4099 rows starting 2010, values $9-$29). Atomic writes + retry helpers
defend against missing/partial data but do not defend against plausibly-
shaped wrong-values data.

This module adds a defensive layer at two points:

1. **Write-time (`assert_plausible`)** — raise `RuntimeError` before any
   `write_parquet_atomic` call. Bad data never touches the cache.

2. **Read-time cross-validation (`cross_validate_last_close`)** — compare
   cached last-close against an independent live source (Alpaca).
   Divergence > threshold → log + record to state + caller-decided action.

State is recorded to `data/risk_state/plausibility_state.json` so the
dashboard can surface failures even if a caller caught the RuntimeError
and retried successfully. See `/api/health/plausibility` endpoint.

Bands are hardcoded here (not a config file) on purpose — each band has
a *reason* that belongs next to the number. If the ticker count grows
past ~15 or per-environment overrides are needed later, lift to JSON.
"""

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

# Module-level state path — risk_state is the existing convention for
# small JSON files that the dashboard polls (filter_state, circuit_breaker,
# validation_state all live here).
STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "risk_state" / "plausibility_state.json"


# ---------------------------------------------------------------------------
# Per-ticker bands — (min_allowed, max_allowed, reason)
# ---------------------------------------------------------------------------
# A series is plausible if *every* value falls inside [min_allowed, max_allowed].
# Any single bar below the floor or above the cap fails the check.
#
# The check was tightened 2026-04-22 after IWM data leaked into vix.parquet
# under concurrent yfinance contamination. IWM's historical range
# ($36–$280+) overlaps VIX's ($5–$100) at the low end, so the earlier
# "entire series must be out of range" variant passed the corrupted cache.
# The bands carry 3-5× headroom over historical extremes, so the tightened
# check has no false-positive risk on real data for banded tickers.
#
# Reasons: all thresholds anchored to verifiable historical facts. If an
# assumption breaks (e.g. BTC crashes to $500 in 2029), update the band
# alongside the reason. Do NOT loosen bands just to make a failure go away.

BANDS: dict[str, tuple[float, float, str]] = {
    "BTC-USD": (
        1000.0,
        500_000.0,
        "BTC has not closed below $1,000 since Dec 2017. $500k upper is 4-5x "
        "current ATH (~$100k) — generous headroom for multi-year growth.",
    ),
    "ETH-USD": (
        50.0,
        20_000.0,
        "ETH has not closed below $80 since Feb 2018 (buffer to $50). "
        "$20k upper is ~4x current ATH.",
    ),
    "SPY": (
        40.0,
        2_000.0,
        "SPY auto-adjusted close bottomed at $49.81 on 2009-03-09 — $40 "
        "floor leaves headroom under the historical low. $2k cap gives "
        "3x+ headroom for long-term growth.",
    ),
    "^VIX": (
        5.0,
        100.0,
        "VIX historical range ~9 (low-vol regime) to ~82 (Oct 2008), "
        "~85 (Mar 2020). $100 cap gives headroom for a worse spike.",
    ),
    "SHY": (
        60.0,
        100.0,
        "Short-term Treasury ETF has traded in a tight $80-$86 band "
        "since inception. $60-$100 gives comfortable rate-regime buffer.",
    ),
}


# ---------------------------------------------------------------------------
# Assertions — raise RuntimeError if values don't match the band
# ---------------------------------------------------------------------------


class PlausibilityError(RuntimeError):
    """Raised when a cached-data candidate fails plausibility checks.

    Caller MUST NOT write the failing data to cache. Log, record state,
    and either retry or fail loud upstream.
    """


def assert_plausible(series: pd.Series, ticker: str) -> None:
    """Raise `PlausibilityError` if series values are implausible for ticker.

    Silently returns (no check) for tickers without a defined band — this
    is intentional so adding a new ticker to the universe doesn't block
    downloads. Only known-ticker violations are loud.

    Records write-time failures + successes to plausibility_state.json so
    the dashboard can surface them.

    Args:
        series: 1-D price series. NaN values are dropped before checking.
        ticker: Ticker name used to look up the band.

    Raises:
        PlausibilityError: If observed max < band floor or observed min > band cap.
            (Both directions are checked — catches "all values are from a different
             asset" in either direction.)
    """
    if ticker not in BANDS:
        return

    min_val, max_val, reason = BANDS[ticker]

    clean = series.dropna()
    if len(clean) == 0:
        # All-NaN series isn't a plausibility failure on its own — the
        # coverage-ratio check in `download_with_retry` handles missing data.
        # Record success so we don't leave stale failures on the dashboard.
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
    """Apply `assert_plausible` to each column of a DataFrame.

    Column names are used as ticker identifiers. Columns whose name is
    not in BANDS are skipped silently. Raises on the first failure.
    """
    if df is None or df.empty:
        return
    for col in df.columns:
        assert_plausible(df[col], str(col))


# ---------------------------------------------------------------------------
# Cross-validation — compare cached last-close to live broker quote
# ---------------------------------------------------------------------------


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
    """Compare cached last-close to an independent live price.

    Records divergences to plausibility_state.json. Does NOT raise —
    caller decides whether to serve, refresh, or block. Threshold default
    5% is generous; a real data-poisoning event (like 2026-04-21 BTC)
    would show 99%+ divergence.

    Args:
        series: Cached price series.
        ticker: Ticker name (used for state-recording key).
        live_price: Price from an independent source (e.g. Alpaca).
        threshold_pct: Allowed relative divergence (0.05 = 5%).

    Returns:
        DivergenceResult. `within_threshold=False` means the caller
        should consider the cache suspect.
    """
    clean = series.dropna()
    if len(clean) == 0:
        # Empty cache — can't compare. Return "within_threshold=True"
        # so callers don't block on this; coverage checks handle empty.
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


# ---------------------------------------------------------------------------
# State file — JSON, keyed by ticker
# ---------------------------------------------------------------------------
#
# Schema:
# {
#   "BTC-USD": {
#     "last_success_at": "2026-04-21T19:15:03+00:00",
#     "last_success_n_obs": 3033,
#     "last_failure_at": "2026-04-21T14:32:11+00:00",   (optional)
#     "last_failure_reason": "observed max=$24.50 below floor $1000",
#     "last_failure_obs_min": 9.12,
#     "last_failure_obs_max": 24.50,
#     "last_failure_n_obs": 4099,
#     "last_divergence_at": "...",   (optional, from cross_validate_last_close)
#     "last_divergence_cached": 24.50,
#     "last_divergence_live": 75312.00,
#     "last_divergence_pct": 3.08
#   },
#   ...
# }
#
# Dashboard logic: ticker has an "active issue" if
#   last_failure_at > (last_success_at OR "epoch")
# OR
#   last_divergence_at is within the last 24h.


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
        # Callers (_record_failure/_success/_divergence) run inside
        # exception-suppressing paths; without an explicit log the write
        # failure disappears silently and the dashboard banner never fires.
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
