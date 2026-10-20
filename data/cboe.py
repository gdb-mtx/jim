"""CBOE volatility indices from the publisher's own daily CSVs.

VIX, VIX9D and VIX3M — free, no key, stable URLs (cdn.cboe.com), history
from 1990. Replaces yfinance's ^VIX / ^VIX9D / ^VIX3M (2026-10-20): Yahoo
republishes CBOE, so this is the primary source.
"""

import io

import pandas as pd
import requests

CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv"
_TIMEOUT_S = 30


def _parse_cboe_csv(text: str, name: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip().upper() for c in df.columns]
    s = pd.Series(df["CLOSE"].astype(float).values,
                  index=pd.to_datetime(df["DATE"], format="%m/%d/%Y"), name=f"^{name}")
    s.index.name = "Date"
    return s.sort_index()


def fetch_cboe_index(name: str) -> pd.Series:
    """Daily closes for `name` in {VIX, VIX9D, VIX3M}, yfinance-style series name (^VIX)."""
    r = requests.get(CBOE_URL.format(name=name), timeout=_TIMEOUT_S, allow_redirects=True)
    r.raise_for_status()
    s = _parse_cboe_csv(r.text, name)
    if len(s) < 1000:
        raise RuntimeError(f"CBOE {name} returned only {len(s)} rows")
    return s
