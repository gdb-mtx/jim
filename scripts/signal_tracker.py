#!/usr/bin/env python3
"""Signal-only vs live return decomposition for A4 crypto.

Reads the rebalance journal to reconstruct what perfect (costless,
instant) execution would have returned, then compares to actual Alpaca
equity from snapshots. The gap is "execution drag" — transaction costs,
slippage, phantom positions, filter whipsaw churn, and infrastructure
incidents.

Usage:
    uv run python3 scripts/signal_tracker.py                    # full history
    uv run python3 scripts/signal_tracker.py --since 2026-05-01 # recent window
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

JOURNAL = PROJECT_ROOT / "data" / "rebalance_log.jsonl"
SNAPSHOTS = PROJECT_ROOT / "data" / "processed" / "snapshots_acct4.parquet"


def load_journal(since: str | None = None) -> list[dict]:
    entries = []
    with open(JOURNAL) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("account") != 4:
                continue
            if since and entry["timestamp"][:10] < since:
                continue
            entries.append(entry)
    return sorted(entries, key=lambda e: e["timestamp"])


def build_signal_weights(journal: list[dict]) -> pd.DataFrame:
    """Build a daily weight series from journal entries.

    Each journal entry defines the weights held from that rebalance until
    the next one. Weights are post_filter_weights × vol_scalar (the final
    target the strategy wanted to hold).
    """
    records = []
    for entry in journal:
        pfw = entry.get("post_filter_weights") or {}
        vs = entry.get("vol_scalar", 1.0)
        weights = {sym: w * vs for sym, w in pfw.items()}
        ts = entry["timestamp"][:10]
        records.append({"date": ts, "weights": weights})

    if not records:
        return pd.DataFrame()

    # Forward-fill weights between rebalances
    start = records[0]["date"]
    end = datetime.now().strftime("%Y-%m-%d")
    dates = pd.date_range(start, end, freq="D")

    weight_by_date = {}
    rec_idx = 0
    current_weights: dict[str, float] = {}
    for d in dates:
        ds = d.strftime("%Y-%m-%d")
        while rec_idx < len(records) and records[rec_idx]["date"] <= ds:
            current_weights = records[rec_idx]["weights"]
            rec_idx += 1
        weight_by_date[d] = dict(current_weights)

    all_symbols = set()
    for w in weight_by_date.values():
        all_symbols.update(w.keys())

    rows = []
    for d in dates:
        row = {sym: weight_by_date[d].get(sym, 0.0) for sym in all_symbols}
        rows.append(row)

    return pd.DataFrame(rows, index=dates)


def main() -> int:
    parser = argparse.ArgumentParser(description="Signal-only vs live return tracker")
    parser.add_argument("--since", type=str, default=None, help="Start date (YYYY-MM-DD)")
    args = parser.parse_args()

    if not JOURNAL.exists():
        print("No rebalance journal found.")
        return 1
    if not SNAPSHOTS.exists():
        print("No snapshots found for account 4.")
        return 1

    journal = load_journal(since=args.since)
    if not journal:
        print("No A4 journal entries found.")
        return 1

    # Build signal weight timeseries
    weights_df = build_signal_weights(journal)
    if weights_df.empty:
        print("No weight data to analyze.")
        return 1

    # Normalize symbol format for Alpaca bars (BTC/USD → BTC-USD for yfinance compat)
    # Alpaca bars use the same index format as the weights
    from data.alpaca_crypto_bars import get_crypto_bars
    prices = get_crypto_bars(start=(args.since or "2026-04-01"))

    # Compute daily returns from prices
    returns = prices.pct_change()

    # Align weights and returns (shift weights by 1 — today's weight earns tomorrow's return)
    common_dates = weights_df.index.intersection(returns.index)
    if len(common_dates) < 2:
        print("Not enough overlapping dates between weights and prices.")
        return 1

    # Map weight symbols (BTC/USD) to price columns (BTC-USD)
    sym_map = {}
    for col in weights_df.columns:
        price_col = col.replace("/", "-")
        if price_col in returns.columns:
            sym_map[col] = price_col

    aligned_weights = weights_df.loc[common_dates].rename(columns=sym_map)
    aligned_returns = returns.loc[common_dates]

    # Only keep columns present in both
    shared_cols = [c for c in aligned_weights.columns if c in aligned_returns.columns]
    signal_daily = (aligned_weights[shared_cols].shift(1) * aligned_returns[shared_cols]).sum(axis=1)
    signal_daily = signal_daily.iloc[1:]  # drop first NaN from shift
    signal_cum = (1 + signal_daily).cumprod()

    # Load live snapshots
    snapshots = pd.read_parquet(SNAPSHOTS)
    live_equity = snapshots["equity"]
    live_start = live_equity.loc[live_equity.index >= common_dates[0]].iloc[0]

    # Align to common dates
    live_on_dates = live_equity.reindex(signal_cum.index)
    live_cum = live_on_dates / live_start

    # Summary
    first_date = signal_cum.index[0].strftime("%Y-%m-%d")
    last_date = signal_cum.index[-1].strftime("%Y-%m-%d")
    sig_ret = (signal_cum.iloc[-1] - 1) * 100
    live_last = live_cum.dropna().iloc[-1] if live_cum.dropna().shape[0] > 0 else float("nan")
    live_ret = (live_last - 1) * 100

    print(f"\nSignal-Only vs Live: Account 4 ({first_date} → {last_date})")
    print(f"  Signal return:    {sig_ret:+.2f}%")
    print(f"  Live return:      {live_ret:+.2f}%")
    print(f"  Execution drag:   {sig_ret - live_ret:+.2f}pp")
    print()

    # Day-by-day table
    print(f"{'Date':<12} {'Signal':>8} {'Sig Cum':>8} {'Live Cum':>8} {'Drag':>8}  Held")
    print("-" * 72)

    for dt in signal_cum.index:
        ds = dt.strftime("%Y-%m-%d")
        sd = signal_daily.loc[dt] * 100
        sc = (signal_cum.loc[dt] - 1) * 100
        lc_val = live_cum.get(dt)
        lc = (lc_val - 1) * 100 if pd.notna(lc_val) else float("nan")
        drag = sc - lc if pd.notna(lc_val) else float("nan")

        # What the signal was holding
        w_dt = weights_df.loc[dt] if dt in weights_df.index else pd.Series()
        held = [s.replace("/USD", "") for s, v in w_dt.items() if v > 0.01]

        lc_str = f"{lc:+7.2f}%" if not np.isnan(lc) else "     --"
        drag_str = f"{drag:+7.2f}" if not np.isnan(drag) else "     --"
        print(f"{ds:<12} {sd:+7.2f}% {sc:+7.2f}% {lc_str} {drag_str}  {held}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
