"""
Data Pipeline — Download and manage market data.

Uses yfinance as primary source. Cross-validate against a second source
before trusting any backtest result (see PLAN.md Section 5: Data Quality).
"""

import os
import threading
import time
import pandas as pd
import yfinance as yf
from pathlib import Path

DATA_DIR = Path(__file__).parent

# Serialize yfinance calls across threads. Concurrent `yf.download` calls
# share mutable global state and can return one thread's payload to a
# different thread's request. Reproduced 2026-04-22 after five concurrent
# calls (^VIX, SPY, 9-coin crypto, 18-ETF, BTC-USD) all came back with the
# same BTC-USD 843-row shape — corrupted the crypto/VIX/SPY-filter caches
# and would have put 50% of Account 4 into XLE had the rebalance fired.
_YFINANCE_LOCK = threading.Lock()


def write_parquet_atomic(df: pd.DataFrame, path: Path | str) -> None:
    """Write a DataFrame to parquet atomically.

    Writes to `path + .tmp`, then `os.replace()` swaps it into place.
    A crash or Ctrl-C mid-write leaves the original file intact (or absent)
    — never partial. Closes AUDIT_MONTH2.md S2.
    """
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(tmp)
    os.replace(tmp, path)


def download_with_retry(
    symbols: list[str],
    start: str,
    end: str | None = None,
    *,
    interval: str = "1d",
    max_retries: int = 3,
    min_coverage_ratio: float = 0.5,
) -> pd.DataFrame:
    """Download adjusted close prices with 3× exponential-backoff retry.

    Raises on persistent failure — callers get either a full DataFrame or
    an exception, never silently-partial data. Validates that the result
    contains at least `min_coverage_ratio` of the requested symbols.

    This is the single retry path for every live-trading yfinance call.
    Closes AUDIT_MONTH2.md S4; same hardening that fixed the 91/451 S&P
    corruption is now shared across `download_prices`, crypto, and BTC.
    """
    if not symbols:
        raise ValueError("symbols list is empty")

    requested = set(symbols)

    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with _YFINANCE_LOCK:
                df = yf.download(
                    symbols,
                    start=start,
                    end=end,
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                )
            if isinstance(df.columns, pd.MultiIndex):
                prices = df["Close"]
            else:
                prices = df[["Close"]]
                prices.columns = symbols

            # Defensive column verification. The lock above should prevent
            # cross-thread contamination, but if yfinance ever returns
            # ticker X under a request for ticker Y, raise instead of
            # caching the wrong asset under the right label.
            extras = set(prices.columns) - requested
            if extras:
                raise RuntimeError(
                    f"yfinance returned unexpected tickers: requested="
                    f"{sorted(symbols)}, got={sorted(prices.columns)}, "
                    f"extras={sorted(extras)}"
                )

            coverage = prices.shape[1] / len(symbols)
            if coverage < min_coverage_ratio:
                raise RuntimeError(
                    f"coverage {prices.shape[1]}/{len(symbols)} below "
                    f"min_coverage_ratio={min_coverage_ratio}"
                )
            return prices.dropna(how="all")
        except Exception as e:
            last_err = e
            print(f"  download attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                time.sleep(2 ** attempt)  # 2s, 4s, 8s

    raise RuntimeError(
        f"download failed after {max_retries} retries for {len(symbols)} symbols: {last_err}"
    )


def download_prices(
    symbols: list[str],
    start: str = "2005-01-01",
    end: str | None = None,
    interval: str = "1d",
) -> pd.DataFrame:
    """Download adjusted close prices for a list of symbols.

    Retries on transient yfinance failure (see download_with_retry).

    Args:
        symbols: List of ticker symbols (e.g., ["SPY", "QQQ", "GLD"])
        start: Start date string (YYYY-MM-DD)
        end: End date string, defaults to today
        interval: Data interval ("1d", "1wk", "1mo")

    Returns:
        DataFrame with DatetimeIndex and one column per symbol (adjusted close)
    """
    return download_with_retry(symbols, start=start, end=end, interval=interval)


def download_and_cache(
    symbols: list[str],
    start: str = "2005-01-01",
    end: str | None = None,
    cache_name: str = "prices",
    max_age_hours: int = 16,
) -> pd.DataFrame:
    """Download prices and cache to parquet file for fast reloading.

    Uses cached data if the file exists, has all requested symbols,
    and is younger than max_age_hours. Otherwise re-downloads.

    Args:
        symbols: List of ticker symbols
        start: Start date
        end: End date
        cache_name: Name for the cache file
        max_age_hours: Re-download if cache is older than this (default 16h)

    Returns:
        DataFrame of prices (from cache if available and fresh)
    """
    import time

    cache_path = DATA_DIR / "raw" / f"{cache_name}.parquet"

    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            cached = pd.read_parquet(cache_path)
            # Extra columns beyond what was requested signal a prior bad
            # write (2026-04-22: spy_filter.parquet ended up with [EFA, SPY]
            # after concurrent download contamination). Treat as corrupt
            # and re-download rather than serving a subset that happens
            # to look right.
            extras = set(cached.columns) - set(symbols)
            if extras:
                print(
                    f"Cache {cache_path.name} has unexpected columns "
                    f"{sorted(extras)} — refreshing"
                )
            elif all(s in cached.columns for s in symbols):
                print(f"Loaded {len(cached)} rows from cache: {cache_path}")
                return cached[symbols]

    print(f"Downloading {len(symbols)} symbols from {start}...")
    prices = download_prices(symbols, start=start, end=end)

    # Plausibility guard (AUDIT_MONTH2 S5). Checks per-column against the
    # BANDS dict — SPY, ETH-USD, BTC-USD, SHY, ^VIX have bands; other ETFs
    # pass through silently. Coverage / staleness is handled elsewhere.
    from data.plausibility import assert_plausible_df
    assert_plausible_df(prices)

    write_parquet_atomic(prices, cache_path)
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
