"""
PEAD Historical Backtest — Research Thread 1.

Establishes the baseline: does post-earnings announcement drift exist
in the S&P 500 over the last 4 quarters? What's the base rate?

Usage:
    # Full backtest (fetches data, caches, analyzes)
    uv run python3 -m mode2.pead_backtest

    # Use cached data only (skip fetching)
    uv run python3 -m mode2.pead_backtest --cached
"""

import json
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

DATA_DIR = Path("data/mode2")
CACHE_PATH = DATA_DIR / "pead_backtest_events.parquet"
PRICES_CACHE = DATA_DIR / "pead_backtest_prices.parquet"

# How many quarters of earnings to look back
NUM_QUARTERS = 5
# Only include events where we have at least this many trading days after
MIN_TRADING_DAYS_AFTER = 65
# Measurement windows (trading days after earnings)
DRIFT_WINDOWS = [1, 5, 10, 20, 40, 60]


def get_sp500_tickers() -> list[str]:
    """Get S&P 500 tickers from cache or Wikipedia."""
    cache_path = Path("data/raw/sp500_tickers.json")
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)
    from data.sp500 import get_sp500_tickers as _get
    return _get()


def fetch_earnings_events(symbols: list[str]) -> pd.DataFrame:
    """Fetch earnings dates + surprise data for all symbols via yfinance.

    Returns DataFrame with: symbol, earnings_date, eps_estimate, eps_actual,
    surprise_pct, report_hour (bmo/amc)
    """
    print(f"Fetching earnings data for {len(symbols)} symbols...")
    all_events = []
    errors = 0
    start_time = time.time()

    for i, sym in enumerate(symbols):
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            remaining = (len(symbols) - i - 1) / rate
            print(f"  {i+1}/{len(symbols)} ({rate:.0f} sym/s, ~{remaining:.0f}s remaining)")

        try:
            t = yf.Ticker(sym)
            ed = t.get_earnings_dates(limit=NUM_QUARTERS * 2)
            if ed is None or len(ed) == 0:
                continue

            reported = ed[ed["Reported EPS"].notna()]
            for idx, row in reported.iterrows():
                # idx is a timezone-aware datetime
                earnings_date = idx.tz_localize(None) if idx.tzinfo else idx
                # Determine if before-market-open or after-market-close
                hour = earnings_date.hour
                report_hour = "bmo" if hour < 12 else "amc"

                all_events.append({
                    "symbol": sym,
                    "earnings_date": earnings_date.normalize(),  # Date only
                    "eps_estimate": row["EPS Estimate"],
                    "eps_actual": row["Reported EPS"],
                    "surprise_pct": row["Surprise(%)"],
                    "report_hour": report_hour,
                })
        except Exception:
            errors += 1

    elapsed = time.time() - start_time
    print(f"  Done: {len(all_events)} events from {len(symbols)} symbols "
          f"({errors} errors) in {elapsed:.0f}s")

    df = pd.DataFrame(all_events)
    if len(df) > 0:
        df["earnings_date"] = pd.to_datetime(df["earnings_date"])
        # Remove duplicates (same symbol + date)
        df = df.drop_duplicates(subset=["symbol", "earnings_date"])
    return df


def download_prices(symbols: list[str], start_date: str) -> pd.DataFrame:
    """Download daily closing prices for all symbols + SPY via yfinance batch."""
    # Always include SPY for market-adjusted returns
    all_symbols = list(set(symbols + ["SPY"]))
    print(f"Downloading prices for {len(all_symbols)} symbols from {start_date}...")
    data = yf.download(
        all_symbols,
        start=start_date,
        end=datetime.now().strftime("%Y-%m-%d"),
        progress=True,
        threads=True,
    )
    # Extract close prices — handle both single and multi-symbol cases
    if isinstance(data.columns, pd.MultiIndex):
        prices = data["Close"]
    else:
        prices = data[["Close"]]
        prices.columns = all_symbols[:1]
    return prices


def calculate_drift(events: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Calculate post-earnings returns at various intervals.

    For BMO (before market open): entry = open on earnings day → measure from that close
    For AMC (after market close): entry = next trading day open → measure from that close

    Simplified: we use closing prices.
    - AMC reports: entry price = next trading day's close (T+1)
    - BMO reports: entry price = earnings day close (T+0)
    """
    results = []
    trading_dates = prices.index

    for _, event in events.iterrows():
        sym = event["symbol"]
        e_date = event["earnings_date"]

        if sym not in prices.columns:
            continue

        sym_prices = prices[sym].dropna()
        if len(sym_prices) == 0:
            continue

        # Find the entry date: next trading day after earnings for AMC,
        # earnings day for BMO. To be safe, always use T+1 (next trading day).
        valid_dates = trading_dates[trading_dates > e_date]
        if len(valid_dates) < MIN_TRADING_DAYS_AFTER:
            continue

        entry_date = valid_dates[0]
        if entry_date not in sym_prices.index:
            continue
        entry_price = sym_prices[entry_date]
        if pd.isna(entry_price) or entry_price <= 0:
            continue

        # Also get pre-earnings price (day before) for gap calculation
        pre_dates = trading_dates[trading_dates < e_date]
        if len(pre_dates) == 0:
            continue
        pre_date = pre_dates[-1]
        pre_price = sym_prices.get(pre_date, np.nan)

        result = {
            "symbol": sym,
            "earnings_date": e_date,
            "eps_estimate": event["eps_estimate"],
            "eps_actual": event["eps_actual"],
            "surprise_pct": event["surprise_pct"],
            "entry_date": entry_date,
            "entry_price": entry_price,
            "pre_price": pre_price,
        }

        # Calculate overnight gap (earnings reaction)
        if not pd.isna(pre_price) and pre_price > 0:
            result["gap_pct"] = (entry_price - pre_price) / pre_price * 100
        else:
            result["gap_pct"] = np.nan

        # Calculate returns at each drift window
        # valid_dates[0] = entry day (T+1 after earnings)
        # valid_dates[1] = T+2, etc.
        # So for N-day drift, use valid_dates[N] (N trading days after entry)
        spy_prices = prices["SPY"].dropna() if "SPY" in prices.columns else pd.Series(dtype=float)
        spy_entry = spy_prices.get(entry_date, np.nan)

        for days in DRIFT_WINDOWS:
            if days < len(valid_dates):
                future_date = valid_dates[days]  # N trading days after entry
                future_price = sym_prices.get(future_date, np.nan)
                if not pd.isna(future_price) and future_price > 0:
                    raw_return = (future_price - entry_price) / entry_price * 100
                    result[f"return_{days}d"] = raw_return

                    # Market-adjusted return (subtract SPY return over same period)
                    spy_future = spy_prices.get(future_date, np.nan)
                    if not pd.isna(spy_entry) and not pd.isna(spy_future) and spy_entry > 0:
                        spy_return = (spy_future - spy_entry) / spy_entry * 100
                        result[f"adj_return_{days}d"] = raw_return - spy_return
                    else:
                        result[f"adj_return_{days}d"] = np.nan
                else:
                    result[f"return_{days}d"] = np.nan
                    result[f"adj_return_{days}d"] = np.nan
            else:
                result[f"return_{days}d"] = np.nan
                result[f"adj_return_{days}d"] = np.nan

        results.append(result)

    return pd.DataFrame(results)


def classify_surprise(surprise_pct: float) -> str:
    """Classify surprise into quintiles."""
    if surprise_pct <= -5:
        return "big_miss"
    elif surprise_pct < -1:
        return "miss"
    elif surprise_pct <= 1:
        return "inline"
    elif surprise_pct <= 5:
        return "beat"
    else:
        return "big_beat"


def analyze_results(df: pd.DataFrame) -> dict:
    """Comprehensive PEAD analysis."""
    # Add surprise classification
    df = df.copy()
    df["surprise_class"] = df["surprise_pct"].apply(classify_surprise)

    # Add surprise quintile
    df["surprise_quintile"] = pd.qcut(
        df["surprise_pct"], 5, labels=["Q1_worst", "Q2", "Q3", "Q4", "Q5_best"]
    )

    report = {}

    # ── Overall Statistics ──
    total = len(df)
    beats = (df["surprise_pct"] > 0).sum()
    report["overview"] = {
        "total_events": total,
        "beats": int(beats),
        "misses": int((df["surprise_pct"] < 0).sum()),
        "inline": int((df["surprise_pct"] == 0).sum()),
        "beat_rate": round(beats / total * 100, 1),
        "avg_surprise": round(df["surprise_pct"].mean(), 2),
        "median_surprise": round(df["surprise_pct"].median(), 2),
    }

    # ── Drift by Surprise Direction (raw and market-adjusted) ──
    for prefix, col_prefix in [("raw", "return"), ("adj", "adj_return")]:
        for direction, mask in [("beats", df["surprise_pct"] > 0),
                                  ("misses", df["surprise_pct"] < 0),
                                  ("all", pd.Series(True, index=df.index))]:
            subset = df[mask]
            drift = {}
            for days in DRIFT_WINDOWS:
                col = f"{col_prefix}_{days}d"
                if col in subset.columns:
                    returns = subset[col].dropna()
                    drift[f"{days}d"] = {
                        "mean": round(returns.mean(), 2),
                        "median": round(returns.median(), 2),
                        "positive_pct": round((returns > 0).sum() / len(returns) * 100, 1) if len(returns) > 0 else 0,
                        "count": len(returns),
                    }
            report[f"{prefix}_drift_{direction}"] = drift

    # ── Drift by Surprise Quintile — both raw and adjusted (THE KEY TABLE) ──
    for prefix, col_prefix in [("raw", "return"), ("adj", "adj_return")]:
        quintile_drift = {}
        for q in ["Q1_worst", "Q2", "Q3", "Q4", "Q5_best"]:
            subset = df[df["surprise_quintile"] == q]
            q_data = {"count": len(subset), "avg_surprise": round(subset["surprise_pct"].mean(), 2)}
            for days in DRIFT_WINDOWS:
                col = f"{col_prefix}_{days}d"
                if col in subset.columns:
                    returns = subset[col].dropna()
                    q_data[f"{days}d_mean"] = round(returns.mean(), 2)
                    q_data[f"{days}d_median"] = round(returns.median(), 2)
                    q_data[f"{days}d_positive_pct"] = round(
                        (returns > 0).sum() / len(returns) * 100, 1
                    ) if len(returns) > 0 else 0
            quintile_drift[q] = q_data
        report[f"{prefix}_by_quintile"] = quintile_drift

    # ── Drift by Surprise Class (market-adjusted) ──
    class_drift = {}
    for cls in ["big_miss", "miss", "inline", "beat", "big_beat"]:
        subset = df[df["surprise_class"] == cls]
        if len(subset) == 0:
            continue
        c_data = {"count": len(subset), "avg_surprise": round(subset["surprise_pct"].mean(), 2)}
        for days in [1, 5, 10, 20, 40, 60]:
            for col_prefix, label in [("return", "raw"), ("adj_return", "adj")]:
                col = f"{col_prefix}_{days}d"
                if col in subset.columns:
                    returns = subset[col].dropna()
                    c_data[f"{label}_{days}d_mean"] = round(returns.mean(), 2)
        class_drift[cls] = c_data
    report["by_class"] = class_drift

    # ── Gap vs Drift (is the gap the whole story, or is there residual drift?) ──
    for prefix, col_60 in [("raw", "return_60d"), ("adj", "adj_return_60d")]:
        if "gap_pct" in df.columns and col_60 in df.columns:
            valid = df[["gap_pct", col_60, "surprise_pct"]].dropna()
            if len(valid) > 10:
                valid = valid.copy()
                valid["post_gap_drift"] = valid[col_60] - valid["gap_pct"]
                report[f"{prefix}_gap_analysis"] = {
                    "avg_gap_beats": round(valid[valid["surprise_pct"] > 0]["gap_pct"].mean(), 2),
                    "avg_gap_misses": round(valid[valid["surprise_pct"] < 0]["gap_pct"].mean(), 2),
                    "avg_post_gap_drift_beats": round(
                        valid[valid["surprise_pct"] > 0]["post_gap_drift"].mean(), 2
                    ),
                    "avg_post_gap_drift_misses": round(
                        valid[valid["surprise_pct"] < 0]["post_gap_drift"].mean(), 2
                    ),
                }

    # ── Spread: Q5 minus Q1 at each window (raw and adjusted) ──
    for prefix in ["raw", "adj"]:
        qd = report.get(f"{prefix}_by_quintile", {})
        if "Q5_best" in qd and "Q1_worst" in qd:
            spread = {}
            for days in DRIFT_WINDOWS:
                q5 = qd["Q5_best"].get(f"{days}d_mean", 0)
                q1 = qd["Q1_worst"].get(f"{days}d_mean", 0)
                spread[f"{days}d"] = round(q5 - q1, 2)
            report[f"{prefix}_q5_q1_spread"] = spread

    return report


def print_report(report: dict):
    """Pretty-print the backtest report."""
    print("\n" + "=" * 70)
    print("PEAD HISTORICAL BACKTEST — S&P 500")
    print("=" * 70)

    ov = report["overview"]
    print(f"\nTotal earnings events: {ov['total_events']}")
    print(f"Beats: {ov['beats']} ({ov['beat_rate']}%)  |  Misses: {ov['misses']}  |  Inline: {ov['inline']}")
    print(f"Avg surprise: {ov['avg_surprise']:+.2f}%  |  Median: {ov['median_surprise']:+.2f}%")

    # Print both raw and market-adjusted tables
    for prefix, label in [("raw", "RAW RETURNS"), ("adj", "MARKET-ADJUSTED (minus SPY)")]:
        # Drift by direction
        print(f"\n{'─' * 70}")
        print(f"POST-EARNINGS DRIFT BY DIRECTION — {label}")
        print(f"{'─' * 70}")
        print(f"{'Window':<10} {'Beats':<12} {'Misses':<12} {'Spread':<10} {'Beat %pos':<10}")
        for days in DRIFT_WINDOWS:
            key = f"{days}d"
            b = report.get(f"{prefix}_drift_beats", {}).get(key, {})
            m = report.get(f"{prefix}_drift_misses", {}).get(key, {})
            spread = round(b.get("mean", 0) - m.get("mean", 0), 2)
            print(f"  {key:<8} {b.get('mean', 0):+.2f}%{'':<6} "
                  f"{m.get('mean', 0):+.2f}%{'':<6} "
                  f"{spread:+.2f}%{'':<4} {b.get('positive_pct', 0):.0f}%")

        # Drift by quintile
        print(f"\n{'─' * 70}")
        print(f"DRIFT BY SURPRISE QUINTILE — {label}")
        print(f"{'─' * 70}")
        print(f"{'Quintile':<12} {'Avg Surp':<10} {'N':<6} {'1d':<8} {'5d':<8} {'10d':<8} {'20d':<8} {'40d':<8} {'60d':<8}")
        qd_all = report.get(f"{prefix}_by_quintile", {})
        for q in ["Q1_worst", "Q2", "Q3", "Q4", "Q5_best"]:
            qd = qd_all.get(q, {})
            print(f"  {q:<10} {qd.get('avg_surprise', 0):+.1f}%{'':<4} {qd.get('count', 0):<6} "
                  f"{qd.get('1d_mean', 0):+.2f}%  "
                  f"{qd.get('5d_mean', 0):+.2f}%  "
                  f"{qd.get('10d_mean', 0):+.2f}%  "
                  f"{qd.get('20d_mean', 0):+.2f}%  "
                  f"{qd.get('40d_mean', 0):+.2f}%  "
                  f"{qd.get('60d_mean', 0):+.2f}%")

        # Q5-Q1 spread
        spread = report.get(f"{prefix}_q5_q1_spread", {})
        if spread:
            print(f"\n  Q5-Q1 spread (long best, short worst):")
            print(f"  ", end="")
            for days in DRIFT_WINDOWS:
                key = f"{days}d"
                print(f"{key}: {spread.get(key, 0):+.2f}%  ", end="")
            print()

    # Gap analysis (market-adjusted)
    ga = report.get("adj_gap_analysis") or report.get("raw_gap_analysis", {})
    if ga:
        is_adj = "adj_gap_analysis" in report
        label = "MARKET-ADJUSTED" if is_adj else "RAW"
        print(f"\n{'─' * 70}")
        print(f"GAP vs POST-GAP DRIFT — {label}")
        print(f"{'─' * 70}")
        print(f"  Beats:  avg gap = {ga['avg_gap_beats']:+.2f}%, "
              f"post-gap drift (60d) = {ga['avg_post_gap_drift_beats']:+.2f}%")
        print(f"  Misses: avg gap = {ga['avg_gap_misses']:+.2f}%, "
              f"post-gap drift (60d) = {ga['avg_post_gap_drift_misses']:+.2f}%")
        beat_drift = ga["avg_post_gap_drift_beats"]
        miss_drift = ga["avg_post_gap_drift_misses"]
        if beat_drift > miss_drift:
            print(f"  ✓ PEAD confirmed: beat drift ({beat_drift:+.2f}%) > miss drift ({miss_drift:+.2f}%)")
        else:
            print(f"  ✗ No PEAD: miss drift ({miss_drift:+.2f}%) >= beat drift ({beat_drift:+.2f}%)")

    # By class (market-adjusted)
    if "by_class" in report:
        print(f"\n{'─' * 70}")
        print("DRIFT BY SURPRISE CATEGORY — MARKET-ADJUSTED")
        print(f"{'─' * 70}")
        print(f"{'Category':<12} {'Avg Surp':<10} {'N':<6} {'1d':<8} {'10d':<8} {'20d':<8} {'60d':<8}")
        for cls in ["big_miss", "miss", "inline", "beat", "big_beat"]:
            cd = report["by_class"].get(cls, {})
            if not cd:
                continue
            print(f"  {cls:<10} {cd.get('avg_surprise', 0):+.1f}%{'':<4} {cd.get('count', 0):<6} "
                  f"{cd.get('adj_1d_mean', 0):+.2f}%  "
                  f"{cd.get('adj_10d_mean', 0):+.2f}%  "
                  f"{cd.get('adj_20d_mean', 0):+.2f}%  "
                  f"{cd.get('adj_60d_mean', 0):+.2f}%")


def run_backtest(use_cached: bool = False):
    """Run the full PEAD backtest."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if use_cached and CACHE_PATH.exists():
        print("Loading cached earnings events...")
        events = pd.read_parquet(CACHE_PATH)
        print(f"  {len(events)} events loaded")
    else:
        symbols = get_sp500_tickers()
        events = fetch_earnings_events(symbols)
        if len(events) == 0:
            print("No earnings events found!")
            return
        events.to_parquet(CACHE_PATH)
        print(f"  Cached to {CACHE_PATH}")

    # Filter to events with enough history for drift measurement
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=MIN_TRADING_DAYS_AFTER + 30)
    events = events[events["earnings_date"] < cutoff]
    print(f"  Events with enough post-earnings history: {len(events)}")

    if len(events) == 0:
        print("No events old enough to measure 60-day drift!")
        return

    # Download prices
    if use_cached and PRICES_CACHE.exists():
        print("Loading cached prices...")
        prices = pd.read_parquet(PRICES_CACHE)
    else:
        earliest = events["earnings_date"].min() - pd.Timedelta(days=5)
        symbols_needed = events["symbol"].unique().tolist()
        prices = download_prices(symbols_needed, earliest.strftime("%Y-%m-%d"))
        prices.to_parquet(PRICES_CACHE)
        print(f"  Cached to {PRICES_CACHE}")

    # Calculate drift
    print("\nCalculating post-earnings drift...")
    results = calculate_drift(events, prices)
    print(f"  {len(results)} events with complete drift data")

    if len(results) < 20:
        print("Not enough data for meaningful analysis!")
        return

    # Save results
    results_path = DATA_DIR / "pead_backtest_results.parquet"
    results.to_parquet(results_path)

    # Analyze and print
    report = analyze_results(results)
    print_report(report)

    # Save report as JSON
    report_path = DATA_DIR / "pead_backtest_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved to {report_path}")

    return report


if __name__ == "__main__":
    import sys
    use_cached = "--cached" in sys.argv
    run_backtest(use_cached=use_cached)
