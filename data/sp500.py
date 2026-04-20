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
import pandas as pd
import yfinance as yf
import requests
from pathlib import Path

DATA_DIR = Path(__file__).parent


def get_sp500_tickers() -> list[str]:
    """Get current S&P 500 constituent tickers.

    Scrapes Wikipedia, caches locally to avoid repeated requests.

    Returns:
        List of ticker symbols (e.g., ["AAPL", "MSFT", ...])
    """
    cache_path = DATA_DIR / "raw" / "sp500_tickers.json"

    if cache_path.exists():
        with open(cache_path) as f:
            tickers = json.load(f)
        print(f"Loaded {len(tickers)} S&P 500 tickers from cache")
        return tickers

    print("Fetching S&P 500 tickers from Wikipedia...")
    resp = requests.get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    tables = pd.read_html(io.StringIO(resp.text))
    sp500 = tables[0]
    tickers = sp500["Symbol"].str.replace(".", "-", regex=False).tolist()

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(tickers, f)
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
    # S&P 500 refresh is slow (~5 minutes for 451 tickers). Use a longer TTL
    # than the other caches, with the expectation that an append-only
    # incremental refresh will eventually replace this full-rebuild path.
    max_age_hours = 24

    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            prices = pd.read_parquet(cache_path)
            print(f"Loaded S&P 500 prices from cache: {prices.shape[0]} rows, {prices.shape[1]} stocks")
            return prices
        print(f"S&P 500 cache is {age_hours:.1f}h old (>{max_age_hours}h) — refreshing (slow)...")

    tickers = get_sp500_tickers()
    if max_tickers:
        tickers = tickers[:max_tickers]

    print(f"Downloading prices for {len(tickers)} S&P 500 stocks from {start}...")
    print("This may take a few minutes on first run...")

    # Download in batches to avoid yfinance timeouts. Retry + >=50%-per-batch
    # coverage guard live in data.pipeline.download_with_retry (S4). If a
    # batch still fails after retries, we raise rather than silently write
    # a truncated cache (prior bug: Apr 20 refresh returned 91/451 tickers
    # and corrupted signals).
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

    # Drop stocks with too many missing values (< 80% coverage)
    min_coverage = 0.80
    coverage = prices.notna().sum() / len(prices)
    good_stocks = coverage[coverage >= min_coverage].index
    prices = prices[good_stocks].dropna(how="all")

    # Forward-fill small gaps (weekends, holidays already handled by yfinance)
    prices = prices.ffill(limit=5)

    print(f"Final universe: {prices.shape[1]} stocks with {min_coverage:.0%}+ coverage")
    print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}")

    from data.pipeline import write_parquet_atomic
    write_parquet_atomic(prices, cache_path)
    print(f"Cached to {cache_path}")

    return prices


def download_vix(start: str = "2005-01-01") -> pd.Series:
    """Download VIX index for regime detection.

    Args:
        start: Start date

    Returns:
        Series of VIX closing values
    """
    import time

    cache_path = DATA_DIR / "raw" / "vix.parquet"
    max_age_hours = 16

    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            vix = pd.read_parquet(cache_path).squeeze()
            print(f"Loaded VIX from cache: {len(vix)} rows")
            return vix
        print(f"VIX cache is {age_hours:.1f}h old (>{max_age_hours}h) — refreshing...")

    print("Downloading VIX data...")
    from data.pipeline import download_with_retry, write_parquet_atomic
    prices = download_with_retry(["^VIX"], start=start, min_coverage_ratio=1.0)
    vix = prices.iloc[:, 0]

    vix.name = "VIX"
    vix_df = vix.to_frame()
    write_parquet_atomic(vix_df, cache_path)
    print(f"Cached VIX: {len(vix)} rows")

    return vix
