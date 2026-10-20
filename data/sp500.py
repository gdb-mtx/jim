"""
S&P 500 Universe — Stock-level data for individual momentum strategies.

Downloads S&P 500 constituent tickers from Wikipedia and manages
price data for the full universe. Uses aggressive caching since
downloading 500 stocks takes time.

Note: This uses the CURRENT S&P 500 list, which introduces survivorship
bias (companies that were removed aren't included). This is a known
limitation — acceptable for strategy development, but results will be
slightly optimistic. See PLAN.md Section 5: Data Quality.
"""

import io
import json
import logging
import threading
import time
import pandas as pd
import requests
from pathlib import Path

DATA_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)

# Single-flight refresh: prevents concurrent callers from interleaving batches and triggering Yahoo 429s.
_SP500_REFRESH_LOCK = threading.Lock()

# Canonical floor for the shared S&P cache. Every write downloads from here
# regardless of the caller's `start`, and a cached frame starting later is
# treated as truncated. 2026-09-08: the 4-hourly macro composite
# (start="2024-01-01") hit the TTL-expired cache and rewrote it as 673 rows;
# every validation/scorecard/backtest then ran on 2024+ data. Same class as
# the 2026-08-10 etf_prices incident (fixed in download_and_cache).
SP500_CACHE_FLOOR = "2010-01-01"
# Last day of the banked yfinance segment's overlap with Alpaca (splice window).
BANKED_OVERLAP_END = "2016-03-31"


def _is_truncated(prices: pd.DataFrame) -> bool:
    return prices.index[0] > pd.Timestamp(SP500_CACHE_FLOOR) + pd.Timedelta(days=7)


def get_sp500_tickers() -> list[str]:
    """Get current S&P 500 constituent tickers.

    Scrapes Wikipedia, caches locally with a 7-day TTL so delisted names fall
    out instead of silently shrinking the 80% coverage filter. On Wikipedia
    failure, falls back to the stale cached list rather than breaking the
    download pipeline.
    """
    cache_path = DATA_DIR / "raw" / "sp500_tickers.json"
    max_age_hours = 24 * 7  # S&P 500 changes ~4x/year; weekly refresh

    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            with open(cache_path) as f:
                tickers = json.load(f)
            print(f"Loaded {len(tickers)} S&P 500 tickers from cache ({age_hours:.1f}h old)")
            return tickers
        print(f"S&P 500 ticker list is {age_hours:.1f}h old (>{max_age_hours}h) — refreshing from Wikipedia...")
    else:
        print("Fetching S&P 500 tickers from Wikipedia...")

    try:
        resp = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        sp500 = tables[0]
        tickers = sp500["Symbol"].str.replace(".", "-", regex=False).tolist()
    except Exception as e:
        if cache_path.exists():
            logger.warning("Wikipedia S&P 500 fetch failed (%s) — falling back to stale cache", e)
            with open(cache_path) as f:
                return json.load(f)
        raise

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(tickers, f)
    tmp_path.replace(cache_path)
    print(f"Cached {len(tickers)} tickers")

    return tickers


def download_sp500_prices(
    start: str = "2010-01-01",
    end: str | None = None,
    max_tickers: int | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Download adjusted close prices for S&P 500 stocks.

    Downloads in batches and caches to parquet for fast reloading.
    Drops stocks with insufficient history (< 80% of trading days).

    Args:
        start: Start date
        end: End date (None = today)
        max_tickers: Limit number of tickers (for testing)

    Returns:
        DataFrame with DatetimeIndex, one column per stock
    """
    import time

    cache_path = DATA_DIR / "raw" / "sp500_prices.parquet"
    # S&P 500 refresh is slow (~5 minutes for ~500 tickers); longer TTL than other caches.
    max_age_hours = 24

    def _is_fresh() -> bool:
        if not cache_path.exists():
            return False
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        return age_hours < max_age_hours

    # Fast path: lock-free read for the common case where the cache is fresh.
    if not force_refresh and _is_fresh():
        prices = pd.read_parquet(cache_path)
        if len(prices) == 0:
            print("S&P 500 cache has 0 rows — refreshing")
        elif _is_truncated(prices):
            print(f"S&P 500 cache starts {prices.index[0].date()} (floor {SP500_CACHE_FLOOR}) — truncated, refreshing")
        else:
            from data.pipeline import content_is_stale
            if content_is_stale(prices):
                print("S&P 500 cache content is stale — refreshing")
            else:
                print(f"Loaded S&P 500 prices from cache: {prices.shape[0]} rows, {prices.shape[1]} stocks")
                return prices

    # Serialize refresh + double-checked re-read after lock release.
    with _SP500_REFRESH_LOCK:
        if not force_refresh and _is_fresh():
            prices = pd.read_parquet(cache_path)
            if len(prices) == 0:
                print("S&P 500 cache has 0 rows — refreshing (after waiting on lock)")
            elif _is_truncated(prices):
                print("S&P 500 cache is truncated — refreshing (after waiting on lock)")
            else:
                from data.pipeline import content_is_stale
                if content_is_stale(prices):
                    print("S&P 500 cache content is stale — refreshing (after waiting on lock)")
                else:
                    print(f"Loaded S&P 500 prices from cache (after waiting on refresh): {prices.shape[0]} rows, {prices.shape[1]} stocks")
                    return prices

        if cache_path.exists():
            age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
            print(f"S&P 500 cache is {age_hours:.1f}h old (>{max_age_hours}h) — refreshing (slow)...")

        tickers = get_sp500_tickers()
        if max_tickers:
            tickers = tickers[:max_tickers]

        # Alpaca SIP from the 2016 floor, spliced onto the one-time banked
        # yfinance segment (data/banked/, scripts/bank_pre2016.py). The full
        # Alpaca range is re-pulled every refresh because adjusted closes are
        # re-based by every dividend — a partial append would mix bases.
        # 2026-10-20: yfinance retired from this path (DATA_SOURCES.md).
        from data.alpaca_equity_bars import ALPACA_EQUITY_FLOOR, get_equity_closes, splice_banked
        banked_path = DATA_DIR / "banked" / "sp500_pre2016.parquet"
        if not banked_path.exists():
            raise RuntimeError(
                f"{banked_path} missing — pre-2016 history is banked once from a trusted "
                f"yfinance cache (scripts/bank_pre2016.py); restore it from backup."
            )
        print(f"Downloading {len(tickers)} S&P 500 stocks from Alpaca SIP ({ALPACA_EQUITY_FLOOR}+)...")
        fresh = get_equity_closes(tickers, start=ALPACA_EQUITY_FLOOR, end=end)
        prices = splice_banked(pd.read_parquet(banked_path), fresh, BANKED_OVERLAP_END)

        # Trailing-window coverage gate so recent S&P additions can qualify; pre-IPO NaNs are NaN-safe.
        coverage_window = min(500, len(prices))
        min_coverage = 0.80
        coverage = prices.tail(coverage_window).notna().sum() / coverage_window
        good_stocks = coverage[coverage >= min_coverage].index
        prices = prices[good_stocks].dropna(how="all")

        # Forward-fill small gaps (weekends, holidays already handled by yfinance)
        prices = prices.ffill(limit=5)

        print(f"Final universe: {prices.shape[1]} stocks with {min_coverage:.0%}+ coverage")
        print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}")

        # Plausibility guard. Individual stocks have no per-ticker bands (prices
        # legitimately span $5-$1000+ and split), so most columns pass silently.
        from data.pipeline import write_parquet_atomic
        from data.plausibility import assert_plausible_df
        assert_plausible_df(prices)

        # A right-truncated (end-bounded) or subset (max_tickers) frame must
        # never become the shared cache.
        if end is None and max_tickers is None:
            from data.trading_dates import drop_unsettled_equity_rows
            prices = drop_unsettled_equity_rows(prices)
            write_parquet_atomic(prices, cache_path)
            print(f"Cached to {cache_path}")
        else:
            print("end/max_tickers request — no cache write")

        return prices


def download_vix(
    start: str = "2005-01-01", force_refresh: bool = False
) -> pd.Series:
    """Download VIX index for regime detection.

    Args:
        start: Start date
        force_refresh: If True, skip cache read and re-fetch from yfinance.

    Returns:
        Series of VIX closing values
    """
    import time

    cache_path = DATA_DIR / "raw" / "vix.parquet"
    max_age_hours = 16

    if not force_refresh and cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            cached_df = pd.read_parquet(cache_path)
            # Schema check — file must contain exactly the renamed VIX column.
            if len(cached_df) == 0:
                print("VIX cache has 0 rows — refreshing")
            elif list(cached_df.columns) != ["VIX"]:
                print(
                    f"VIX cache has unexpected columns {list(cached_df.columns)} "
                    f"— refreshing"
                )
            else:
                vix = cached_df.squeeze()
                # Read-time plausibility check — catches silent cache corruption.
                # File stores name="VIX" but bands are keyed on "^VIX".
                from data.plausibility import assert_plausible, PlausibilityError
                try:
                    vix_check = vix.copy()
                    vix_check.name = "^VIX"
                    assert_plausible(vix_check, "^VIX")
                except PlausibilityError as e:
                    print(f"VIX cache failed plausibility ({e}) — refreshing")
                else:
                    from data.pipeline import content_is_stale
                    if content_is_stale(cached_df):
                        print("VIX cache content is stale — refreshing")
                    else:
                        print(f"Loaded VIX from cache: {len(vix)} rows")
                        return vix
        else:
            print(f"VIX cache is {age_hours:.1f}h old (>{max_age_hours}h) — refreshing...")

    print("Downloading VIX data...")
    from data.pipeline import write_parquet_atomic
    from data.plausibility import assert_plausible
    from data.cboe import fetch_cboe_index
    # CBOE's own CSV — the primary publisher; yfinance republished it (2026-10-20).
    vix = fetch_cboe_index("VIX").loc[start:]
    vix.name = "^VIX"  # keep ticker name for plausibility lookup

    # Plausibility guard. VIX band 5-100; anything outside is yfinance garbage.
    assert_plausible(vix, "^VIX")

    vix.name = "VIX"  # restore display name for downstream consumers
    vix_df = vix.to_frame()
    from data.trading_dates import drop_unsettled_equity_rows
    vix_df = drop_unsettled_equity_rows(vix_df)
    write_parquet_atomic(vix_df, cache_path)
    print(f"Cached VIX: {len(vix)} rows")

    return vix


def download_spy(force_refresh: bool = False) -> pd.DataFrame:
    """SPY daily closes for the 200d trend filter — single-column frame
    (`SPY`), cache `spy_filter.parquet`, 16h TTL + settled-session content
    check. Alpaca SIP from 2016 spliced onto the banked yfinance segment
    (2005-2016). Replaces `download_and_cache(["SPY"], cache_name="spy_filter")`
    at every live/validation call site (2026-10-20). Live code may still
    overlay the latest Alpaca price on the last row (compute_spy_trend_filter).
    """
    import time

    cache_path = DATA_DIR / "raw" / "spy_filter.parquet"
    max_age_hours = 16
    if not force_refresh and cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            cached = pd.read_parquet(cache_path)
            from data.pipeline import content_is_stale
            if len(cached) > 0 and list(cached.columns) == ["SPY"] and not content_is_stale(cached):
                return cached
            print("SPY cache stale/invalid — refreshing")
        else:
            print(f"SPY cache is {age_hours:.1f}h old (>{max_age_hours}h) — refreshing...")

    from data.alpaca_equity_bars import ALPACA_EQUITY_FLOOR, get_equity_closes, splice_banked
    from data.pipeline import write_parquet_atomic
    from data.plausibility import assert_plausible_df
    from data.trading_dates import drop_unsettled_equity_rows
    banked_path = DATA_DIR / "banked" / "spy_pre2016.parquet"
    if not banked_path.exists():
        raise RuntimeError(f"{banked_path} missing — run scripts/bank_pre2016.py from a trusted cache")
    fresh = get_equity_closes(["SPY"], start=ALPACA_EQUITY_FLOOR)
    spy = splice_banked(pd.read_parquet(banked_path)[["SPY"]], fresh, BANKED_OVERLAP_END)
    spy = drop_unsettled_equity_rows(spy)
    assert_plausible_df(spy)
    write_parquet_atomic(spy, cache_path)
    print(f"Cached SPY: {len(spy)} rows")
    return spy
