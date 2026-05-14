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
import yfinance as yf
import requests
from pathlib import Path

DATA_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)

# Single-flight refresh: prevents concurrent callers from interleaving batches and triggering Yahoo 429s.
_SP500_REFRESH_LOCK = threading.Lock()


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
    if _is_fresh():
        prices = pd.read_parquet(cache_path)
        if len(prices) == 0:
            print("S&P 500 cache has 0 rows — refreshing")
        else:
            from data.pipeline import content_is_stale
            if content_is_stale(prices):
                print("S&P 500 cache content is stale — refreshing")
            else:
                print(f"Loaded S&P 500 prices from cache: {prices.shape[0]} rows, {prices.shape[1]} stocks")
                return prices

    # Serialize refresh + double-checked re-read after lock release.
    with _SP500_REFRESH_LOCK:
        if _is_fresh():
            prices = pd.read_parquet(cache_path)
            if len(prices) == 0:
                print("S&P 500 cache has 0 rows — refreshing (after waiting on lock)")
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

        print(f"Downloading prices for {len(tickers)} S&P 500 stocks from {start}...")
        print("This may take a few minutes on first run...")

        # Batched download; raise on persistent batch failure rather than write a truncated cache.
        from data.pipeline import download_with_retry
        batch_size = 50
        all_prices = []
        failed_batches: list[int] = []

        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(tickers) - 1) // batch_size + 1
            print(f"  Batch {batch_num}/{total_batches}: {len(batch)} tickers")

            try:
                batch_prices = download_with_retry(
                    batch, start=start, end=end, min_coverage_ratio=0.5
                )
            except Exception as e:
                print(f"  Batch {batch_num} exhausted retries: {e}")
                failed_batches.append(batch_num)
            else:
                all_prices.append(batch_prices)

        if failed_batches:
            raise RuntimeError(
                f"S&P 500 download failed for batches {failed_batches} after "
                f"retries exhausted. Refusing to write a truncated cache. "
                f"Retry later (likely yfinance rate-limit) or investigate."
            )

        prices = pd.concat(all_prices, axis=1)

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

        write_parquet_atomic(prices, cache_path)
        print(f"Cached to {cache_path}")

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
    from data.pipeline import download_with_retry, write_parquet_atomic
    from data.plausibility import assert_plausible
    prices = download_with_retry(["^VIX"], start=start, min_coverage_ratio=1.0)
    vix = prices.iloc[:, 0]
    vix.name = "^VIX"  # keep ticker name for plausibility lookup

    # Plausibility guard. VIX band 5-100; anything outside is yfinance garbage.
    assert_plausible(vix, "^VIX")

    vix.name = "VIX"  # restore display name for downstream consumers
    vix_df = vix.to_frame()
    write_parquet_atomic(vix_df, cache_path)
    print(f"Cached VIX: {len(vix)} rows")

    return vix
