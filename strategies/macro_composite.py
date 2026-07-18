"""Book-level macro composite — five price-based stress sensors → exposure scalar.

Gap 3 (regime adaptivity) from BOOK_SHAPE: the SPY 200d filter de-risked
months after the 2022 top. This composite votes on five daily,
publication-lag-free market prices and scales the whole book's exposure.
Deliberately no ML, no FRED, no tunable weights — the spec below was
pre-registered before the first evaluation run (see
docs/research/MACRO_COMPOSITE_EVAL.md) and must not be re-tuned against
the same history that motivated it.

Components (1 stress vote each):
  credit   HYG/IEF ratio below its 100d SMA      (credit leads equity)
  dollar   UUP above its 100d SMA                (dollar up = liquidity drain)
  vix_ts   VIX9D/VIX3M >= 1.0                    (term-structure inversion)
  breadth  % of S&P 500 above own 200d < 40%     (narrowing participation)
  defense  XLU/SPY ratio above its 100d SMA      (defensive rotation)

Vote → scalar map (fixed): 0-1 → 1.00, 2 → 0.85, 3 → 0.70, 4 → 0.55,
5 → 0.40. A single sensor never de-risks (whipsaw guard); two independent
stress signals are required to cut a dollar of exposure.

Missing data (e.g. VIX9D pre-2011) = no vote from that sensor — the
composite degrades toward 1.0, never toward stress, on data gaps.
"""

import logging

import numpy as np
import pandas as pd

log = logging.getLogger("fire.macro_composite")

SMA_DAYS = 100
BREADTH_MA_DAYS = 200
BREADTH_STRESS = 0.40
VIX_TS_STRESS = 1.00
SCALAR_MAP = {0: 1.00, 1: 1.00, 2: 0.85, 3: 0.70, 4: 0.55, 5: 0.40}


def compute_macro_composite(
    etf_prices: pd.DataFrame,
    vix9d: pd.Series | None = None,
    vix3m: pd.Series | None = None,
    sp500_prices: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compute daily component votes and the composite scalar.

    Args:
        etf_prices: Daily closes with columns HYG, IEF, UUP, XLU, SPY.
        vix9d, vix3m: ^VIX9D / ^VIX3M closes (optional — no vote if absent).
        sp500_prices: Full S&P 500 close panel for the breadth sensor
            (optional — no vote if absent).

    Returns:
        DataFrame indexed like etf_prices with columns: one 0/1 vote per
        sensor (NaN where that sensor has no data), `votes` (sum of
        available votes), `scalar` (mapped exposure scalar, un-shifted —
        callers must lag by one day before applying to returns).
    """
    idx = etf_prices.index
    out = pd.DataFrame(index=idx)

    ratio = etf_prices["HYG"] / etf_prices["IEF"]
    out["credit"] = (ratio < ratio.rolling(SMA_DAYS).mean()).astype(float).where(
        ratio.rolling(SMA_DAYS).mean().notna()
    )
    uup = etf_prices["UUP"]
    out["dollar"] = (uup > uup.rolling(SMA_DAYS).mean()).astype(float).where(
        uup.rolling(SMA_DAYS).mean().notna()
    )
    defense = etf_prices["XLU"] / etf_prices["SPY"]
    out["defense"] = (defense > defense.rolling(SMA_DAYS).mean()).astype(float).where(
        defense.rolling(SMA_DAYS).mean().notna()
    )

    if vix9d is not None and vix3m is not None:
        ts = (vix9d / vix3m).reindex(idx).ffill(limit=5)
        out["vix_ts"] = (ts >= VIX_TS_STRESS).astype(float).where(ts.notna())
    else:
        out["vix_ts"] = np.nan

    if sp500_prices is not None and len(sp500_prices.columns) > 50:
        above = sp500_prices > sp500_prices.rolling(BREADTH_MA_DAYS).mean()
        valid = sp500_prices.notna() & sp500_prices.rolling(BREADTH_MA_DAYS).mean().notna()
        breadth = above[valid].sum(axis=1) / valid.sum(axis=1).replace(0, np.nan)
        breadth = breadth.reindex(idx).ffill(limit=5)
        out["breadth"] = (breadth < BREADTH_STRESS).astype(float).where(breadth.notna())
    else:
        out["breadth"] = np.nan

    out["votes"] = out[["credit", "dollar", "vix_ts", "breadth", "defense"]].sum(
        axis=1, min_count=1
    )
    out["scalar"] = out["votes"].map(lambda v: SCALAR_MAP.get(int(v), 0.40) if pd.notna(v) else 1.0)
    out.loc[out["votes"].isna(), "scalar"] = 1.0
    return out


def compute_live_macro_state() -> dict:
    """Today's composite votes for the filter monitor (alert-only surface).

    Self-contained data pull: five ETFs + VIX pair from yfinance, breadth
    from the cached S&P 500 panel. Returns a flat dict of floats for
    filter_state.json. Raises on data failure — the caller treats macro
    fields as optional and must not let this block the SPY filter.

    Per docs/research/MACRO_COMPOSITE_EVAL.md the scalar is NOT applied to
    live weights (rejected by the pre-registered evaluation — the book's
    existing de-risk stack makes it pure bull-cost); it exists for alerting
    and downstream timing (e.g. the VIXY tail leg).
    """
    import yfinance as yf

    from data.sp500 import download_sp500_prices

    px = yf.download(
        ["HYG", "IEF", "UUP", "XLU", "SPY", "^VIX9D", "^VIX3M"],
        period="2y", progress=False, auto_adjust=True,
    )["Close"]
    sp500 = download_sp500_prices(start="2024-01-01")
    comp = compute_macro_composite(
        px[["HYG", "IEF", "UUP", "XLU", "SPY"]].dropna(subset=["HYG", "IEF"]),
        vix9d=px["^VIX9D"], vix3m=px["^VIX3M"], sp500_prices=sp500,
    )
    last = comp.iloc[-1]
    return {
        "macro_votes": float(last["votes"]) if pd.notna(last["votes"]) else 0.0,
        "macro_scalar": float(last["scalar"]),
        "macro_credit": float(last["credit"]) if pd.notna(last["credit"]) else -1.0,
        "macro_dollar": float(last["dollar"]) if pd.notna(last["dollar"]) else -1.0,
        "macro_vix_ts": float(last["vix_ts"]) if pd.notna(last["vix_ts"]) else -1.0,
        "macro_breadth": float(last["breadth"]) if pd.notna(last["breadth"]) else -1.0,
        "macro_defense": float(last["defense"]) if pd.notna(last["defense"]) else -1.0,
    }
