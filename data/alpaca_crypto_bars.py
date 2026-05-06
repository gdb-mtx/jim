"""Alpaca crypto bars — broker-native price source for live signal computation.

Why Alpaca for live (yfinance still backs backtest, see data/crypto.py):
- Same source the broker uses internally → no third-party publishing delay.
  yfinance has a 1-12h delay between UTC-midnight bar close and the settled
  value being available in the API (see HISTORY.md C10). Alpaca produces
  bars from its own trade tape, so yesterday's settled bar is available
  within seconds of UTC midnight.
- We already authenticate to Alpaca for trading; same key, no separate signup.
- No third-party caching layer drift (the failure class behind nearly every
  yfinance incident in DATA_SOURCES.md).

What still applies post-migration:
- Daily bars are stamped at the bar's UTC-midnight start, same as yfinance.
- The latest bar at query time is partial (its close = current scratch
  price) until UTC midnight rolls. The C9 fix in
  CryptoMomentum.generate_signals (drop today's partial bar before computing
  momentum) continues to apply — same behaviour, same fix.

Universe: BNB-USD is unavailable on Alpaca (regulatory non-listing post 2023
SEC v. Binance enforcement). data.crypto.LIVE_CRYPTO_UNIVERSE is the 8-coin
subset Alpaca lists; the wrapper silently drops any symbol Alpaca returns no
bars for, so callers can pass either universe and get back what's tradeable.

Cache: none by design. Each call fetches fresh. The whole point of the
migration is to bypass cache-staleness; Alpaca's API is fast enough that
1-2 calls per A4 fire is cheap.
"""

import os
from typing import Iterable

import pandas as pd
import requests
from dotenv import load_dotenv

from data.crypto import (
    LIVE_CRYPTO_UNIVERSE,
    to_alpaca_symbol,
    to_yfinance_symbol,
)

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

API_BASE = "https://data.alpaca.markets/v1beta3/crypto/us"
_TIMEOUT_S = 30


def _auth_headers() -> dict[str, str]:
    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if not api_key or not secret:
        raise RuntimeError(
            "ALPACA_API_KEY / ALPACA_SECRET_KEY must be set in .env"
        )
    return {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret}


def _fetch_bars_paginated(
    alpaca_symbols: Iterable[str], start: str, end: str | None
) -> dict[str, list[dict]]:
    """Walk next_page_token until exhausted. Returns {alpaca_sym: [bar dicts]}.

    Bar dict keys: t, o, h, l, c, v, n, vw (per Alpaca docs).
    """
    syms = list(alpaca_symbols)
    out: dict[str, list[dict]] = {s: [] for s in syms}
    next_token: str | None = None
    while True:
        params: dict = {
            "symbols": ",".join(syms),
            "timeframe": "1Day",
            "start": start,
            "limit": 10000,
            "sort": "asc",
        }
        if end is not None:
            params["end"] = end
        if next_token:
            params["page_token"] = next_token
        r = requests.get(
            f"{API_BASE}/bars",
            headers=_auth_headers(),
            params=params,
            timeout=_TIMEOUT_S,
        )
        r.raise_for_status()
        body = r.json()
        for sym, bars in (body.get("bars") or {}).items():
            if sym in out:
                out[sym].extend(bars)
        next_token = body.get("next_page_token")
        if not next_token:
            break
    return out


def get_crypto_bars(
    symbols: list[str] | None = None,
    start: str = "2021-01-01",
    end: str | None = None,
) -> pd.DataFrame:
    """Daily crypto close prices from Alpaca, yfinance-shaped for drop-in use.

    Returns:
        DataFrame with tz-naive DatetimeIndex (UTC-midnight bar starts) and
        one column per coin in yfinance form (BTC-USD, not BTC/USD). Coins
        Alpaca has no bars for (e.g. BNB-USD passed by mistake) are silently
        dropped — callers see only what's actually tradeable.

    Args:
        symbols: yfinance-form symbols. Default: LIVE_CRYPTO_UNIVERSE.
        start: ISO date. Alpaca's earliest crypto bar is 2021-01-01 for the
            longest-history coins; newer listings start later.
        end: ISO date upper bound. None = up to current.
    """
    if symbols is None:
        symbols = list(LIVE_CRYPTO_UNIVERSE)
    alpaca_symbols = [to_alpaca_symbol(s) for s in symbols]
    bars_by_sym = _fetch_bars_paginated(alpaca_symbols, start=start, end=end)

    series_by_yf: dict[str, pd.Series] = {}
    for alpaca_sym, bars in bars_by_sym.items():
        if not bars:
            continue
        df = pd.DataFrame(bars)
        df["t"] = pd.to_datetime(df["t"]).dt.tz_localize(None)
        df = df.set_index("t").sort_index()
        yf_sym = to_yfinance_symbol(alpaca_sym)
        series_by_yf[yf_sym] = df["c"].rename(yf_sym).astype(float)

    if not series_by_yf:
        return pd.DataFrame()
    return pd.concat(series_by_yf.values(), axis=1)


def get_btc_bars(start: str = "2021-01-01") -> pd.Series:
    """BTC daily close series, drop-in replacement for download_btc_prices().

    Returns yfinance-shaped Series named "BTC-USD", tz-naive DatetimeIndex.
    Raises if Alpaca returns no BTC bars (would only happen on outage).
    """
    df = get_crypto_bars(["BTC-USD"], start=start)
    if "BTC-USD" not in df.columns:
        raise RuntimeError("Alpaca returned no BTC/USD bars")
    return df["BTC-USD"]
