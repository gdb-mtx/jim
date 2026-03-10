"""
Data Pipeline — Download and manage market data.

Uses yfinance as primary source. Cross-validate against a second source
before trusting any backtest result (see PLAN.md Section 5: Data Quality).
"""

import pandas as pd
import yfinance as yf
from pathlib import Path

DATA_DIR = Path(__file__).parent


def download_prices(
    symbols: list[str],
    start: str = "2005-01-01",
    end: str | None = None,
    interval: str = "1d",
) -> pd.DataFrame:
    """Download adjusted close prices for a list of symbols.

    Args:
        symbols: List of ticker symbols (e.g., ["SPY", "QQQ", "GLD"])
        start: Start date string (YYYY-MM-DD)
        end: End date string, defaults to today
        interval: Data interval ("1d", "1wk", "1mo")

    Returns:
        DataFrame with DatetimeIndex and one column per symbol (adjusted close)
    """
    df = yf.download(symbols, start=start, end=end, interval=interval, auto_adjust=True)

    if isinstance(df.columns, pd.MultiIndex):
        prices = df["Close"]
    else:
        prices = df[["Close"]]
        prices.columns = symbols

    prices = prices.dropna(how="all")
    return prices


def download_and_cache(
    symbols: list[str],
    start: str = "2005-01-01",
    end: str | None = None,
    cache_name: str = "prices",
) -> pd.DataFrame:
    """Download prices and cache to parquet file for fast reloading.

    Args:
        symbols: List of ticker symbols
        start: Start date
        end: End date
        cache_name: Name for the cache file

    Returns:
        DataFrame of prices (from cache if available and fresh)
    """
    cache_path = DATA_DIR / "raw" / f"{cache_name}.parquet"

    if cache_path.exists():
        cached = pd.read_parquet(cache_path)
        # Check if cache has all requested symbols
        if all(s in cached.columns for s in symbols):
            print(f"Loaded {len(cached)} rows from cache: {cache_path}")
            return cached

    print(f"Downloading {len(symbols)} symbols from {start}...")
    prices = download_prices(symbols, start=start, end=end)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    prices.to_parquet(cache_path)
    print(f"Cached {len(prices)} rows to: {cache_path}")

    return prices


def get_returns(prices: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    """Calculate percentage returns from price data.

    Args:
        prices: DataFrame of prices
        periods: Number of periods for return calculation (1 = daily returns)

    Returns:
        DataFrame of returns
    """
    return prices.pct_change(periods).dropna()


# Default universe from strategies.yaml
DEFAULT_UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD", "DBC"]

# Expanded universe — adds US sector ETFs for better cross-sectional dispersion
SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLU", "XLY", "XLRE"]
EXPANDED_UNIVERSE = DEFAULT_UNIVERSE + SECTOR_ETFS
