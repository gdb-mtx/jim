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

# 9-coin universe — top liquid cryptos available on both yfinance and Alpaca
CRYPTO_UNIVERSE = [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "ADA-USD",
    "AVAX-USD", "LINK-USD", "DOT-USD", "XRP-USD",
]

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


def download_crypto_prices(
    symbols: list[str] | None = None,
    start: str = "2020-01-01",
    end: str | None = None,
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
    cache_path = DATA_DIR / "raw" / "crypto_prices.parquet"

    if cache_path.exists():
        prices = pd.read_parquet(cache_path)
        print(f"Loaded crypto prices from cache: {prices.shape[0]} rows, {prices.shape[1]} coins")
        return prices

    if symbols is None:
        symbols = CRYPTO_UNIVERSE

    print(f"Downloading prices for {len(symbols)} cryptos from {start}...")
    df = yf.download(symbols, start=start, end=end, auto_adjust=True, progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        prices = df["Close"]
    else:
        prices = df[["Close"]]
        prices.columns = symbols

    # Drop coins with too many missing values (< 50% coverage)
    coverage = prices.notna().sum() / len(prices)
    good_coins = coverage[coverage >= 0.50].index
    prices = prices[good_coins].dropna(how="all")

    # Forward-fill small gaps (weekends sometimes have gaps in yfinance crypto)
    prices = prices.ffill(limit=3)

    print(f"Final universe: {prices.shape[1]} coins with 50%+ coverage")
    print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()}")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    prices.to_parquet(cache_path)
    print(f"Cached to {cache_path}")

    return prices


def download_btc_prices(start: str = "2018-01-01") -> pd.Series:
    """Download BTC close prices for the BTC trend filter.

    Analogous to data/sp500.py download_vix() — single-ticker cache.

    Args:
        start: Start date (needs history for 200-day MA warmup)

    Returns:
        Series of BTC/USD closing prices
    """
    cache_path = DATA_DIR / "raw" / "btc_prices.parquet"

    if cache_path.exists():
        btc = pd.read_parquet(cache_path).squeeze()
        print(f"Loaded BTC prices from cache: {len(btc)} rows")
        return btc

    print("Downloading BTC price data...")
    df = yf.download("BTC-USD", start=start, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        btc = df["Close"].squeeze()
    else:
        btc = df["Close"].squeeze()

    btc.name = "BTC-USD"
    btc_df = btc.to_frame()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    btc_df.to_parquet(cache_path)
    print(f"Cached BTC prices: {len(btc)} rows")

    return btc
