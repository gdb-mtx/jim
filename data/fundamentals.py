"""Frozen-shares market-cap helper for the cap-weight research diagnostic.

We store close prices only — no historical market caps anywhere. For a
*directional* "is the SPY gap weighting or picks" test, frozen shares
(current shares outstanding x historical price) is adequate: the concentration
effect is driven by mega-caps whose size *ordering* is robust to share-count
error. This is NOT production-grade weighting — buybacks/splits/issuance make
per-stock caps 5-20% off historically. See
docs/research/BREAKTHROUGH_VECTORS_MAY2026.md.

Research-only. Lives in data/ (no imports from backtesting/), so a live-safe
strategy can consume caps via injection without breaking the
strategies/portfolio_config.py import invariant.
"""

import logging
import pandas as pd
import yfinance as yf
from pathlib import Path

from data.pipeline import write_parquet_atomic

DATA_DIR = Path(__file__).parent
SHARES_CACHE = DATA_DIR / "raw" / "shares_outstanding.parquet"
logger = logging.getLogger(__name__)


def _fetch_one(ticker: str) -> float | None:
    """Current shares outstanding for one ticker, or None if unavailable.

    Tries fast_info (cheap/reliable) then falls back to .info.
    """
    tkr = yf.Ticker(ticker)
    for getter in (
        lambda: tkr.fast_info["shares"],
        lambda: tkr.info.get("sharesOutstanding"),
    ):
        try:
            v = getter()
            if v:
                return float(v)
        except Exception:
            continue
    return None


def get_shares_outstanding(tickers, force_refresh: bool = False) -> pd.Series:
    """Current shares outstanding per ticker (frozen snapshot, cached to parquet).

    Returns a Series indexed by ticker, reindexed to `tickers` (NaN where a
    share count can't be fetched — callers treat a missing cap as 0 weight).
    Only ever-failing tickers are re-attempted on subsequent runs; successes
    persist.
    """
    tickers = list(dict.fromkeys(tickers))  # dedupe, preserve order

    cached = pd.Series(dtype="float64")
    if SHARES_CACHE.exists() and not force_refresh:
        cached = pd.read_parquet(SHARES_CACHE)["shares"]

    missing = [t for t in tickers if t not in cached.index]
    if missing:
        logger.info(
            "Fetching shares outstanding for %d tickers (%d already cached)...",
            len(missing), len(cached),
        )
        fetched: dict[str, float] = {}

        def _persist():
            # Incremental write so a slow/interrupted 500-ticker fetch keeps progress.
            if fetched:
                merged = pd.concat([cached, pd.Series(fetched, dtype="float64")])
                write_parquet_atomic(merged.to_frame("shares"), SHARES_CACHE)

        for i, t in enumerate(missing, 1):
            shares = _fetch_one(t)
            if shares and shares > 0:
                fetched[t] = shares
            if i % 50 == 0:
                logger.info("  ...%d/%d", i, len(missing))
                _persist()
        _persist()
        if fetched:
            cached = pd.concat([cached, pd.Series(fetched, dtype="float64")])
        n_failed = len(missing) - len(fetched)
        if n_failed:
            logger.warning(
                "No shares data for %d/%d fetched tickers (omitted from caps)",
                n_failed, len(missing),
            )

    return cached.reindex(tickers)


def build_market_caps(prices: pd.DataFrame, force_refresh: bool = False) -> pd.DataFrame:
    """Historical market caps = frozen current shares x historical price.

    Same shape as `prices` (DatetimeIndex x ticker columns). Columns with no
    shares data come out all-NaN; the strategy's cap-weight branch drops those
    names to 0 weight. Caps are recomputed each call (cheap); only the shares
    snapshot is cached.
    """
    shares = get_shares_outstanding(list(prices.columns), force_refresh=force_refresh)
    return prices.mul(shares.reindex(prices.columns), axis=1)
