"""yfinance data download + parquet caching."""

import os
import threading
import time
import pandas as pd
import yfinance as yf
from pathlib import Path

DATA_DIR = Path(__file__).parent

# Serialize yfinance: concurrent yf.download shares mutable globals and can cross-contaminate payloads.
_YFINANCE_LOCK = threading.Lock()


def write_parquet_atomic(df: pd.DataFrame, path: Path | str) -> None:
    """Atomic parquet write via tmp + os.replace."""
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
    """Download adjusted closes with 3× exponential-backoff retry. Raises on persistent failure."""
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

            extras = set(prices.columns) - requested
            if extras:
                raise RuntimeError(
                    f"yfinance returned unexpected tickers: requested="
                    f"{sorted(symbols)}, got={sorted(prices.columns)}, "
                    f"extras={sorted(extras)}"
                )

            # yfinance silently drops failed tickers mid-batch. Retry just the missing ones.
            missing = requested - set(prices.columns)
            if missing and len(missing) < len(symbols):
                print(
                    f"  yfinance silently dropped {len(missing)}/{len(symbols)} "
                    f"tickers; retrying just those: {sorted(missing)}"
                )
                with _YFINANCE_LOCK:
                    fill_df = yf.download(
                        list(missing),
                        start=start,
                        end=end,
                        interval=interval,
                        auto_adjust=True,
                        progress=False,
                    )
                if isinstance(fill_df.columns, pd.MultiIndex):
                    fill_prices = fill_df["Close"]
                else:
                    fill_prices = fill_df[["Close"]]
                    fill_prices.columns = list(missing)
                fill_extras = set(fill_prices.columns) - missing
                if fill_extras:
                    raise RuntimeError(
                        f"missing-ticker retry returned unexpected columns: "
                        f"requested={sorted(missing)}, got={sorted(fill_prices.columns)}"
                    )
                recovered = sorted(set(fill_prices.columns) & missing)
                if recovered:
                    print(f"  recovered {len(recovered)}/{len(missing)}: {recovered}")
                    prices = pd.concat([prices, fill_prices], axis=1)
                still_missing = missing - set(fill_prices.columns)
                if still_missing:
                    print(
                        f"  {len(still_missing)} ticker(s) absent on retry "
                        f"(likely legitimate): {sorted(still_missing)}"
                    )

            coverage = prices.shape[1] / len(symbols)
            if coverage < min_coverage_ratio:
                raise RuntimeError(
                    f"coverage {prices.shape[1]}/{len(symbols)} below "
                    f"min_coverage_ratio={min_coverage_ratio}"
                )
            prices = prices.dropna(how="all")
            if len(prices) == 0:
                raise RuntimeError(
                    f"download returned 0 rows for {len(symbols)} symbols "
                    f"(likely no internet or yfinance outage)"
                )
            return prices
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
    """Download adjusted closes; retries on transient yfinance failure."""
    return download_with_retry(symbols, start=start, end=end, interval=interval)


def download_and_cache(
    symbols: list[str],
    start: str = "2005-01-01",
    end: str | None = None,
    cache_name: str = "prices",
    max_age_hours: int = 16,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Download prices with parquet cache. force_refresh skips read but still writes on success."""
    import time

    cache_path = DATA_DIR / "raw" / f"{cache_name}.parquet"

    if not force_refresh and cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            cached = pd.read_parquet(cache_path)
            # Extra columns = prior bad write (concurrent-download contamination); treat as corrupt.
            extras = set(cached.columns) - set(symbols)
            if len(cached) == 0:
                print(f"Cache {cache_path.name} has 0 rows — refreshing")
            elif extras:
                print(
                    f"Cache {cache_path.name} has unexpected columns "
                    f"{sorted(extras)} — refreshing"
                )
            elif all(s in cached.columns for s in symbols):
                print(f"Loaded {len(cached)} rows from cache: {cache_path}")
                return cached[symbols]

    print(f"Downloading {len(symbols)} symbols from {start}...")
    prices = download_prices(symbols, start=start, end=end)

    from data.plausibility import assert_plausible_df
    assert_plausible_df(prices)

    write_parquet_atomic(prices, cache_path)
    print(f"Cached {len(prices)} rows to: {cache_path}")

    return prices


def get_returns(prices: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    return prices.pct_change(periods).dropna()


# Default universe from strategies.yaml
DEFAULT_UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD", "DBC"]

# Expanded universe — adds US sector ETFs for better cross-sectional dispersion
SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLU", "XLY", "XLRE"]
EXPANDED_UNIVERSE = DEFAULT_UNIVERSE + SECTOR_ETFS
