"""
Crypto Data Pipeline — Price data for crypto momentum strategies.

Caches daily crypto closes to parquet (consistent with data/sp500.py) and
manages symbol mapping between yfinance format (BTC-USD) and Alpaca format
(BTC/USD). Since 2026-08-13 the caches are Alpaca-sourced for every bar
inside a coin's Alpaca listing range, with banked yfinance history filling
earlier dates (Alpaca floor 2021+, ragged per coin); settled bars only.
yfinance remains for the BNB column (best-effort) and the bootstrap path.
See DATA_SOURCES.md.
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


def _drop_unsettled(df: pd.DataFrame) -> pd.DataFrame:
    """Drop today's forming bar and any future-dated rows (UTC-day basis).

    The cache stores settled bars only (since 2026-08-13). Both Alpaca and
    yfinance include the current UTC day's partial bar in responses; a
    partial written to the cache becomes a wrong "settled" value forever
    (the C9 contamination class).
    """
    today_utc = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)
    return df.loc[df.index < today_utc]


def download_crypto_prices(
    symbols: list[str] | None = None,
    start: str = "2020-01-01",
    end: str | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Daily crypto close prices: Alpaca-sourced where Alpaca has bars,
    banked yfinance history everywhere else (see DATA_SOURCES.md 2026-08-13).

    On refresh, every bar inside a coin's Alpaca listing range is (re)written
    from Alpaca — self-healing, settled bars only. Dates before a coin's
    Alpaca listing keep the banked yfinance values already in the cache.
    BNB (not listed on Alpaca) appends best-effort from yfinance and never
    blocks the refresh. yfinance is only load-bearing on the bootstrap path
    (cache missing/corrupt → pre-Alpaca history must be re-downloaded).

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
        # end-bounded requests serve a slice of the shared cache — never a
        # separate download, and never a cache write (a right-truncated
        # frame must never become the shared cache).
        prices = download_crypto_prices(
            symbols=symbols, start="2020-01-01", force_refresh=force_refresh
        )
        return prices.loc[start:end]

    # --- Refresh: banked history + Alpaca overwrite -----------------------
    from data.alpaca_crypto_bars import get_crypto_bars
    from data.pipeline import write_parquet_atomic
    from data.plausibility import assert_plausible_df

    # Banked history = the existing cache minus any unsettled tail. Read it
    # even under force_refresh — force refreshes the Alpaca region, it does
    # not discard pre-Alpaca history (which Alpaca cannot re-supply: per-coin
    # listing floors are ragged, e.g. ADA relisted 2026-02, XRP 2024-01).
    banked = pd.DataFrame()
    if cache_path.exists():
        old = pd.read_parquet(cache_path)
        if len(old) > 0 and not (set(old.columns) - set(CRYPTO_UNIVERSE)):
            banked = _drop_unsettled(old)

    if len(banked) == 0:
        # Bootstrap (cache missing/corrupt): pre-Alpaca history only exists
        # on yfinance. Full universe from the 2020 floor regardless of the
        # caller's start/symbols — a short-lookback or subset caller must
        # never shrink the shared cache (2026-08-10 incident). Require >=80%
        # of the 9-coin universe returned; less means a yfinance hiccup.
        print(f"Bootstrapping crypto cache from yfinance ({len(CRYPTO_UNIVERSE)} coins, 2020-01-01)...")
        from data.pipeline import download_with_retry
        banked = download_with_retry(
            CRYPTO_UNIVERSE, start="2020-01-01", end=None, min_coverage_ratio=0.8
        )
        coverage = banked.notna().sum() / len(banked)
        banked = banked[coverage[coverage >= 0.50].index].dropna(how="all")
        banked = _drop_unsettled(banked)

    print(f"Refreshing crypto cache from Alpaca ({len(LIVE_CRYPTO_UNIVERSE)} coins) over banked history...")
    alpaca = _drop_unsettled(get_crypto_bars(list(LIVE_CRYPTO_UNIVERSE), start="2021-01-01"))
    missing = set(LIVE_CRYPTO_UNIVERSE) - set(alpaca.columns)
    if missing:
        raise RuntimeError(
            f"Alpaca returned no bars for {sorted(missing)} — refusing to write crypto cache"
        )

    # BNB: best-effort yfinance append (backtest-only coin, HISTORY.md C11).
    # Failure keeps the banked BNB column as-is and never blocks the refresh.
    bnb = pd.DataFrame()
    try:
        recent = (pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)
                  - pd.Timedelta(days=14)).strftime("%Y-%m-%d")
        raw = yf.download("BNB-USD", start=recent, auto_adjust=True, progress=False)
        if raw is not None and len(raw) > 0:
            closes = raw["Close"] if "Close" in raw else raw
            bnb = _drop_unsettled(closes)[["BNB-USD"]].astype(float)
    except Exception as e:
        print(f"BNB yfinance append failed ({e}) — keeping banked BNB values")

    # Precedence: Alpaca > fresh BNB > banked. combine_first aligns on the
    # union index, so per-coin Alpaca listing gaps fall through to banked.
    prices = alpaca.combine_first(bnb).combine_first(banked) if len(bnb) else alpaca.combine_first(banked)
    prices = prices.sort_index().ffill(limit=3)
    prices.index.name = "Date"

    print(f"Date range: {prices.index[0].date()} to {prices.index[-1].date()} ({prices.shape[1]} coins)")

    # Plausibility guard. Columns without a band (most of the 9-coin universe)
    # pass silently; BTC-USD / ETH-USD raise loudly if wrong.
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

    # --- Refresh: banked history + Alpaca overwrite (see download_crypto_prices) ---
    from data.alpaca_crypto_bars import get_btc_bars
    from data.pipeline import write_parquet_atomic
    from data.plausibility import assert_plausible

    banked = pd.DataFrame()
    if cache_path.exists():
        old = pd.read_parquet(cache_path)
        if len(old) > 0 and list(old.columns) == ["BTC-USD"]:
            banked = _drop_unsettled(old)

    if len(banked) == 0:
        # Bootstrap (cache missing/corrupt): pre-2021 history only exists on
        # yfinance (Alpaca's BTC floor is 2021-01-01; ours is 2018).
        print("Bootstrapping BTC cache from yfinance (2018-01-01)...")
        from data.pipeline import download_with_retry
        banked = download_with_retry(["BTC-USD"], start="2018-01-01", min_coverage_ratio=1.0)
        banked.columns = ["BTC-USD"]
        banked = _drop_unsettled(banked)

    print("Refreshing BTC cache from Alpaca over banked history...")
    fresh = _drop_unsettled(get_btc_bars(start="2021-01-01").to_frame())

    btc_df = fresh.combine_first(banked).sort_index()
    btc_df.index.name = "Date"
    btc = btc_df["BTC-USD"]

    assert_plausible(btc, "BTC-USD")

    write_parquet_atomic(btc_df, cache_path)
    print(f"Cached BTC prices: {len(btc)} rows")

    return btc
