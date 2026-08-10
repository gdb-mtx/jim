"""
Crypto Data Pipeline — Price data for crypto momentum strategies.

Downloads daily crypto prices via yfinance and manages symbol mapping
between yfinance format (BTC-USD) and Alpaca format (BTC/USD).
Uses parquet caching consistent with data/sp500.py pattern.
"""

import pandas as pd
import yfinance as yf
from pathlib import Path

DATA_DIR = Path(__file__).parent

# 9-coin backtest universe (yfinance); 8-coin live universe excludes BNB (Alpaca non-listing, HISTORY.md C11).
CRYPTO_UNIVERSE = [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "ADA-USD",
    "AVAX-USD", "LINK-USD", "DOT-USD", "XRP-USD",
]
LIVE_CRYPTO_UNIVERSE = [s for s in CRYPTO_UNIVERSE if s != "BNB-USD"]

# yfinance ↔ Alpaca symbol mapping
YFINANCE_TO_ALPACA = {
    "BTC-USD": "BTC/USD",
    "ETH-USD": "ETH/USD",
    "SOL-USD": "SOL/USD",
    "BNB-USD": "BNB/USD",
    "ADA-USD": "ADA/USD",
    "AVAX-USD": "AVAX/USD",
    "LINK-USD": "LINK/USD",
    "DOT-USD": "DOT/USD",
    "XRP-USD": "XRP/USD",
}
ALPACA_TO_YFINANCE = {v: k for k, v in YFINANCE_TO_ALPACA.items()}


def to_alpaca_symbol(yf_symbol: str) -> str:
    """Convert yfinance symbol to Alpaca format. 'BTC-USD' → 'BTC/USD'."""
    return YFINANCE_TO_ALPACA.get(yf_symbol, yf_symbol.replace("-", "/"))


def to_yfinance_symbol(alpaca_symbol: str) -> str:
    """Convert Alpaca symbol to yfinance format. 'BTC/USD' → 'BTC-USD'."""
    return ALPACA_TO_YFINANCE.get(alpaca_symbol, alpaca_symbol.replace("/", "-"))


# Alpaca's position list returns crypto symbols without a slash (e.g. `BTCUSD`),
# but orders and price quotes use the slashed form (`BTC/USD`). This map
# normalizes the position form to the order form so the rebalance diff engine
# doesn't treat `BTCUSD` and `BTC/USD` as two different assets.
_ALPACA_POSITION_TO_ORDER = {s.replace("/", ""): s for s in YFINANCE_TO_ALPACA.values()}


def normalize_alpaca_position_symbol(symbol: str) -> str:
    """Normalize Alpaca's position-API crypto symbol to the order-API form.

    'BTCUSD' → 'BTC/USD'. Non-crypto symbols pass through unchanged.
    """
    return _ALPACA_POSITION_TO_ORDER.get(symbol, symbol)


def download_crypto_prices(
    symbols: list[str] | None = None,
    start: str = "2020-01-01",
    end: str | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Download daily crypto close prices via yfinance.

    Caches to parquet for fast reloading. Drops coins with < 50% coverage.

    Args:
        symbols: List of yfinance tickers (default: CRYPTO_UNIVERSE)
        start: Start date
        end: End date (None = today)

    Returns:
        DataFrame with DatetimeIndex, one column per crypto
    """
    import time

    # Clamp to the crypto-universe data floor. Several 9-coin universe
    # members launched 2016-2021, so a pre-2020 fetch returns sparse data
    # that gets dropped by the 50% coverage gate — silently shrinking the
    # universe to 2 coins. (BTC uses a separate 2018 floor in download_btc_prices.)
    if start < "2020-01-01":
        print(f"download_crypto_prices: clamping start {start} → 2020-01-01")
        start = "2020-01-01"

    cache_path = DATA_DIR / "raw" / "crypto_prices.parquet"
    max_age_hours = 16

    if symbols is None:
        symbols = CRYPTO_UNIVERSE

    if not force_refresh and cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            prices = pd.read_parquet(cache_path)
            # Schema check — cache must only contain tickers from the
            # crypto universe. 2026-04-22 corruption left [XLE, ^VIX] here
            # from concurrent-download cross-contamination; a read-time
            # refusal would have stopped the bad rebalance preview.
            extras = set(prices.columns) - set(CRYPTO_UNIVERSE)
            if len(prices) == 0:
                print("Crypto cache has 0 rows — refreshing")
            elif extras:
                print(
                    f"Crypto cache has non-crypto tickers {sorted(extras)} "
                    f"— refreshing"
                )
            else:
                from data.pipeline import content_is_stale
                if content_is_stale(prices, asset_class="crypto"):
                    print("Crypto cache content is stale — refreshing")
                else:
                    present = [s for s in symbols if s in prices.columns]
                    print(f"Loaded crypto prices from cache: {prices.shape[0]} rows, {len(present)} coins")
                    return prices[present]
        else:
            print(f"Crypto cache is {age_hours:.1f}h old (>{max_age_hours}h) — refreshing...")

    if end is not None:
        # end-bounded requests bypass the cache write — a right-truncated
        # frame must never become the shared cache.
        print(f"Downloading prices for {len(symbols)} cryptos from {start} to {end} (no cache write)...")
        from data.pipeline import download_with_retry
        return download_with_retry(
            symbols, start=start, end=end, min_coverage_ratio=0.8
        ).ffill(limit=3)

    # Download the FULL universe from the 2020 floor regardless of the
    # caller's start/symbols — a short-lookback or subset caller must never
    # shrink the shared cache. 2026-08-10: the Monday scorecard cron rewrote
    # this cache as 8 coins from 2025 (was 9 from 2020); twin fix for
    # etf_prices lives in data/pipeline.py download_and_cache.
    print(f"Downloading prices for {len(CRYPTO_UNIVERSE)} cryptos from 2020-01-01...")
    from data.pipeline import download_with_retry, write_parquet_atomic
    # Require >=80% of the 9-coin universe returned; anything less points to
    # a yfinance hiccup, not delisted coins.
    prices = download_with_retry(
        CRYPTO_UNIVERSE, start="2020-01-01", end=None, min_coverage_ratio=0.8
    )

    # Drop coins with too many missing values (< 50% historical coverage)
    coverage = prices.notna().sum() / len(prices)
    good_coins = coverage[coverage >= 0.50].index
    prices = prices[good_coins].dropna(how="all")

    # Forward-fill small gaps (weekends sometimes have gaps in yfinance crypto)
    prices = prices.ffill(limit=3)

    print(f"Final universe: {prices.shape[1]} coins with 50%+ coverage")
    print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}")

    # Plausibility guard. Columns without a band (most of the 9-coin universe)
    # pass silently; BTC-USD / ETH-USD raise loudly if wrong.
    from data.plausibility import assert_plausible_df
    assert_plausible_df(prices)

    write_parquet_atomic(prices, cache_path)
    print(f"Cached to {cache_path}")

    # Same subset contract as the cache-hit path.
    present = [s for s in symbols if s in prices.columns]
    return prices[present]


def download_btc_prices(
    start: str = "2018-01-01", force_refresh: bool = False
) -> pd.Series:
    """Download BTC close prices for the BTC trend filter.

    Analogous to data/sp500.py download_vix() — single-ticker cache.

    Args:
        start: Start date (needs history for 200-day MA warmup)
        force_refresh: If True, skip cache read and re-fetch from yfinance.
            Used by filter_check.py so the BTC filter is never evaluated on
            a stale cached price.

    Returns:
        Series of BTC/USD closing prices
    """
    import time

    # Clamp to project floor (plausibility band + IS validation anchor at 2018).
    if start < "2018-01-01":
        print(f"download_btc_prices: clamping start {start} → 2018-01-01")
        start = "2018-01-01"

    cache_path = DATA_DIR / "raw" / "btc_prices.parquet"
    max_age_hours = 16

    if not force_refresh and cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < max_age_hours:
            cached_df = pd.read_parquet(cache_path)
            # Schema check — file must contain exactly the BTC-USD column.
            if len(cached_df) == 0:
                print("BTC cache has 0 rows — refreshing")
            elif list(cached_df.columns) != ["BTC-USD"]:
                print(
                    f"BTC cache has unexpected columns {list(cached_df.columns)} "
                    f"— refreshing"
                )
            else:
                btc = cached_df.squeeze()
                # Read-time plausibility check — catches silent cache corruption.
                from data.plausibility import assert_plausible, PlausibilityError
                try:
                    btc_check = btc.copy()
                    btc_check.name = "BTC-USD"
                    assert_plausible(btc_check, "BTC-USD")
                except PlausibilityError as e:
                    print(f"BTC cache failed plausibility ({e}) — refreshing")
                else:
                    from data.pipeline import content_is_stale
                    if content_is_stale(cached_df, asset_class="crypto"):
                        print("BTC cache content is stale — refreshing")
                    else:
                        print(f"Loaded BTC prices from cache: {len(btc)} rows")
                        return btc
        else:
            print(f"BTC cache is {age_hours:.1f}h old (>{max_age_hours}h) — refreshing...")

    print("Downloading BTC price data...")
    from data.pipeline import download_with_retry, write_parquet_atomic
    from data.plausibility import assert_plausible
    prices = download_with_retry(["BTC-USD"], start=start, min_coverage_ratio=1.0)
    btc = prices.iloc[:, 0]
    btc.name = "BTC-USD"

    assert_plausible(btc, "BTC-USD")

    btc_df = btc.to_frame()
    write_parquet_atomic(btc_df, cache_path)
    print(f"Cached BTC prices: {len(btc)} rows")

    return btc
