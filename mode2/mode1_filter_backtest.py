"""
Breakthrough #1 Test — Can Claude concentrate Mode 1 alpha as a filter?

Test design (from HUNT_APR2026.md):
1. For each monthly rebalance date, rank S&P 500 stocks by 9-month momentum
   (skip last month) and take the top 30.
2. Pull the most recent pre-rebalance earnings transcript for each name.
3. Claude scores each 1-5 on forward conviction (blind).
4. Portfolio M = top-15 by momentum (Account 1 baseline).
   Portfolio C = top-15 by Claude score, ties broken by momentum rank.
5. Compare 30-day forward returns. Decision thresholds:
     >=1.5%/mo excess: BUILD filter layer
     0.5-1.5%:         3-mo paper trial
     <0.5%:            Kill Mode 2

This file generates the candidate universes (step 1) — the deterministic part.
Transcript fetch and scoring happen in later stages.
"""

import json
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

from data.sp500 import download_sp500_prices


REBALANCE_DATES = [
    "2025-12-01",
    "2026-01-05",
    "2026-02-02",
    "2026-03-02",
    "2026-04-07",
]

LOOKBACK_DAYS = 189
SKIP_RECENT = 21
TOP_N = 30
FORWARD_DAYS = 30

OUT_DIR = Path("data/mode2/mode1_filter")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def compute_momentum_rank(prices: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """9-month return skip-1-month, ranked descending. Returns DataFrame with
    columns [symbol, momentum, rank] for the top universe on `asof`.
    """
    if asof not in prices.index:
        asof = prices.index[prices.index.get_indexer([asof], method="pad")[0]]

    end_idx = prices.index.get_loc(asof)
    lagged_idx = end_idx - SKIP_RECENT
    start_idx = end_idx - LOOKBACK_DAYS

    if start_idx < 0:
        raise ValueError(f"Not enough history before {asof}")

    lagged_price = prices.iloc[lagged_idx]
    older_price = prices.iloc[start_idx]
    momentum = (lagged_price - older_price) / older_price

    momentum = momentum.dropna()
    ranked = momentum.sort_values(ascending=False)

    return pd.DataFrame({
        "symbol": ranked.index,
        "momentum": ranked.values,
        "rank": range(1, len(ranked) + 1),
    })


def forward_return(prices: pd.DataFrame, symbol: str, start: pd.Timestamp, days: int) -> float | None:
    """Forward return over `days` calendar days. Uses pad-alignment on both ends."""
    if symbol not in prices.columns:
        return None
    idx = prices.index
    if start not in idx:
        start = idx[idx.get_indexer([start], method="pad")[0]]
    end_target = start + pd.Timedelta(days=days)
    if end_target > idx.max():
        return None
    end = idx[idx.get_indexer([end_target], method="pad")[0]]

    p0 = prices.loc[start, symbol]
    p1 = prices.loc[end, symbol]
    if pd.isna(p0) or pd.isna(p1):
        return None
    return float(p1 / p0 - 1)


def build_candidate_universes():
    prices = download_sp500_prices(start="2022-01-01")
    print(f"Loaded {prices.shape[1]} stocks, {prices.index.min().date()} -> {prices.index.max().date()}")

    per_date_rows = []
    all_symbols = set()

    for date_str in REBALANCE_DATES:
        asof = pd.Timestamp(date_str)
        ranked = compute_momentum_rank(prices, asof)
        top = ranked.head(TOP_N).copy()
        top["rebalance_date"] = date_str

        fwd = []
        has_fwd = True
        for sym in top["symbol"]:
            r = forward_return(prices, sym, asof, FORWARD_DAYS)
            fwd.append(r)
            if r is None:
                has_fwd = False
        top["fwd_30d_return"] = fwd
        top["has_forward_data"] = has_fwd

        per_date_rows.append(top)
        all_symbols.update(top["symbol"].tolist())

        n_fwd = sum(1 for r in fwd if r is not None)
        print(
            f"  {date_str}: top30 selected, "
            f"{n_fwd}/{TOP_N} have 30d forward returns, "
            f"momentum range {top['momentum'].min():.1%} -> {top['momentum'].max():.1%}"
        )

    universes = pd.concat(per_date_rows, ignore_index=True)
    universes_path = OUT_DIR / "candidate_universes.parquet"
    universes.to_parquet(universes_path)

    symbols_path = OUT_DIR / "unique_symbols.json"
    with open(symbols_path, "w") as f:
        json.dump(sorted(all_symbols), f, indent=2)

    print()
    print(f"Wrote {len(universes)} (date, symbol) rows to {universes_path}")
    print(f"Unique symbols across {len(REBALANCE_DATES)} dates: {len(all_symbols)}")
    print(f"Symbol list: {symbols_path}")

    return universes


if __name__ == "__main__":
    build_candidate_universes()
