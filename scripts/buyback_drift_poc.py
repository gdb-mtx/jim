"""Mid-cap buyback announcement drift — 1-day kill test (POC).

The shelved GO from the April 2026 A5 hunt (docs/archive/HUNT_APR2026.md).
Harvests 8-K share-repurchase-authorization announcements from EDGAR
full-text search, then runs an event study: enter at close T+5 trading days
after the filing, hold 63 trading days, measure return vs SPY and MDY.

Kill criteria (fixed before first run, per the hunt's protocol):
  KILL      mid-cap ($2-20B) mean 63d abnormal < +0.5% or t-stat < 1.0
  GO        mid-cap mean 63d abnormal >= +1.2%, t-stat >= 1.5,
            and 2024+ subsample mean >= 0
  MARGINAL  anything between

Caveats reported, not hidden: yfinance survivorship (missing/delisted
tickers counted), overlapping event windows understate the t-stat's std,
market cap at event approximated as current shares x split-adjusted price.

Usage:
  uv run python3 scripts/buyback_drift_poc.py            # use caches
  uv run python3 scripts/buyback_drift_poc.py --refresh  # re-harvest EDGAR
"""

import argparse
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "research_cache")
EVENTS_CSV = os.path.join(CACHE_DIR, "buyback_events.csv")
SHARES_CSV = os.path.join(CACHE_DIR, "buyback_shares.csv")
PRICES_PQ = os.path.join(CACHE_DIR, "buyback_prices.parquet")

FTS_URL = "https://efts.sec.gov/LATEST/search-index"
UA = {"User-Agent": "George Borshukov gdborshukov@gmail.com (FIRE research)"}
PHRASES = [
    '"new share repurchase program"',
    '"new stock repurchase program"',
    '"authorized a share repurchase program"',
]
QUARTERS = [
    (f"{y}-{q[0]}", f"{y}-{q[1]}")
    for y in range(2022, 2026)
    for q in [("01-01", "03-31"), ("04-01", "06-30"), ("07-01", "09-30"), ("10-01", "12-31")]
] + [("2026-01-01", "2026-03-31")]  # 2026Q1: freshest events with complete 63d windows

TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,9})(?:,[^)]*)?\)\s+\(CIK")
BENCH = ["SPY", "MDY"]
HORIZONS = [21, 42, 63]
ENTRY_LAG = 5
MAX_PAGES = 10  # FTS pages are 10 hits; cap 100 hits per phrase-quarter


def harvest_events() -> pd.DataFrame:
    rows = []
    for start, end in QUARTERS:
        for phrase in PHRASES:
            for page in range(MAX_PAGES):
                params = {"q": phrase, "forms": "8-K", "startdt": start, "enddt": end}
                if page:
                    params["from"] = page * 10
                r = requests.get(FTS_URL, params=params, headers=UA, timeout=30)
                if r.status_code != 200:
                    print(f"  FTS {r.status_code} on {phrase} {start} p{page}, skipping page")
                    break
                hits = r.json().get("hits", {}).get("hits", [])
                for h in hits:
                    src = h["_source"]
                    names = src.get("display_names") or [""]
                    m = TICKER_RE.search(names[0])
                    if not m:
                        continue
                    rows.append(
                        {
                            "ticker": m.group(1).replace(".", "-"),  # yfinance style
                            "cik": (src.get("ciks") or [""])[0],
                            "file_date": src["file_date"],
                            "items": ";".join(src.get("items") or []),
                            "company": names[0].split("  (")[0],
                        }
                    )
                time.sleep(0.12)
                if len(hits) < 10:
                    break
        print(f"  harvested through {end}: {len(rows)} raw hits")
    df = pd.DataFrame(rows).drop_duplicates(subset=["ticker", "file_date"])
    # plain common-stock tickers only (skip units/warrants/preferreds)
    df = df[df["ticker"].str.fullmatch(r"[A-Z]{1,5}(-[A-Z])?")]
    df["file_date"] = pd.to_datetime(df["file_date"])
    df = df.sort_values(["ticker", "file_date"])
    # one event per ticker per 90 calendar days (repeat mentions of same program)
    keep = []
    last: dict[str, pd.Timestamp] = {}
    for _, row in df.iterrows():
        prev = last.get(row["ticker"])
        if prev is None or (row["file_date"] - prev).days > 90:
            keep.append(True)
            last[row["ticker"]] = row["file_date"]
        else:
            keep.append(False)
    df = df[pd.Series(keep, index=df.index)]
    return df.reset_index(drop=True)


def fetch_shares(tickers: list[str]) -> pd.DataFrame:
    import yfinance as yf

    def one(t):
        try:
            return t, float(yf.Ticker(t).fast_info["shares"])
        except Exception:
            return t, np.nan

    with ThreadPoolExecutor(max_workers=8) as ex:
        out = list(ex.map(one, tickers))
    return pd.DataFrame(out, columns=["ticker", "shares"])


def fetch_prices(tickers: list[str]) -> pd.DataFrame:
    import yfinance as yf

    frames = []
    todo = sorted(set(tickers) | set(BENCH))
    for i in range(0, len(todo), 100):
        chunk = todo[i : i + 100]
        px = yf.download(chunk, start="2021-06-01", progress=False, auto_adjust=True)["Close"]
        if isinstance(px, pd.Series):
            px = px.to_frame(chunk[0])
        frames.append(px)
        print(f"  prices {i + len(chunk)}/{len(todo)}")
    out = pd.concat(frames, axis=1)
    out = out.loc[:, ~out.columns.duplicated()]
    out.index = pd.to_datetime(out.index)
    return out


def event_study(events: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    idx = px.index
    recs = []
    for _, ev in events.iterrows():
        t = ev["ticker"]
        if t not in px.columns:
            recs.append({**ev, "status": "no_prices"})
            continue
        s = px[t].dropna()
        pos = idx.searchsorted(ev["file_date"])  # first trading day >= filing
        entry_pos = pos + ENTRY_LAG
        if entry_pos >= len(idx):
            recs.append({**ev, "status": "too_recent"})
            continue
        entry_day = idx[entry_pos]
        if entry_day not in s.index or pd.isna(s.get(entry_day)):
            recs.append({**ev, "status": "no_entry_px"})
            continue
        rec = {**ev, "status": "ok", "entry_date": entry_day, "entry_px": s[entry_day]}
        for h in HORIZONS:
            xp = entry_pos + h
            if xp >= len(idx) or idx[xp] not in s.index or pd.isna(s.get(idx[xp])):
                rec[f"ret_{h}"] = np.nan
                continue
            r = s[idx[xp]] / s[entry_day] - 1
            rec[f"ret_{h}"] = r
            for b in BENCH:
                br = px[b][idx[xp]] / px[b][entry_day] - 1
                rec[f"ab{b.lower()}_{h}"] = r - br
        recs.append(rec)
    return pd.DataFrame(recs)


def bucket(cap):
    if pd.isna(cap):
        return "unknown"
    if cap < 2e9:
        return "small<2B"
    if cap <= 20e9:
        return "mid2-20B"
    return "large>20B"


def table(df: pd.DataFrame, col: str, by=None) -> pd.DataFrame:
    groups = [("ALL", df)] if by is None else list(df.groupby(by))
    rows = []
    for name, g in groups:
        x = g[col].dropna()
        if len(x) < 3:
            rows.append({"group": name, "N": len(x)})
            continue
        t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std(ddof=1) > 0 else np.nan
        rows.append(
            {
                "group": name,
                "N": len(x),
                "mean": f"{x.mean():+.2%}",
                "median": f"{x.median():+.2%}",
                "hit": f"{(x > 0).mean():.0%}",
                "t": f"{t:.2f}",
            }
        )
    return pd.DataFrame(rows).set_index("group")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-harvest EDGAR + shares + prices")
    args = ap.parse_args()
    os.makedirs(CACHE_DIR, exist_ok=True)

    if args.refresh or not os.path.exists(EVENTS_CSV):
        print("Harvesting EDGAR full-text search…")
        events = harvest_events()
        events.to_csv(EVENTS_CSV, index=False)
    else:
        events = pd.read_csv(EVENTS_CSV, parse_dates=["file_date"])
    print(f"Events: {len(events)} across {events['ticker'].nunique()} tickers")

    if args.refresh or not os.path.exists(SHARES_CSV):
        print("Fetching shares outstanding…")
        fetch_shares(sorted(events["ticker"].unique())).to_csv(SHARES_CSV, index=False)
    shares = pd.read_csv(SHARES_CSV).set_index("ticker")["shares"]

    if args.refresh or not os.path.exists(PRICES_PQ):
        print("Fetching prices…")
        fetch_prices(events["ticker"].tolist()).to_parquet(PRICES_PQ)
    px = pd.read_parquet(PRICES_PQ)

    res = event_study(events, px)
    ok = res[res["status"] == "ok"].copy()
    n_missing = (res["status"] == "no_prices").sum() + (res["status"] == "no_entry_px").sum()
    print(f"\nUsable events: {len(ok)} | missing prices (survivorship risk): {n_missing} "
          f"({n_missing / max(len(res), 1):.0%}) | too recent: {(res['status'] == 'too_recent').sum()}")

    # approx cap at event: current shares x split-adjusted entry price
    ok["cap"] = ok.apply(lambda r: shares.get(r["ticker"], np.nan) * r["entry_px"], axis=1)
    ok["bucket"] = ok["cap"].map(bucket)
    ok["year"] = ok["file_date"].dt.year
    ok["pure_801"] = ok["items"].fillna("").str.contains("8.01") & ~ok["items"].fillna("").str.contains("2.02")

    print("\n=== 63d abnormal return vs SPY, by cap bucket ===")
    print(table(ok, "abspy_63", "bucket"))
    print("\n=== 63d abnormal vs MDY (mid-cap benchmark), by bucket ===")
    print(table(ok, "abmdy_63", "bucket"))

    mid = ok[ok["bucket"] == "mid2-20B"]
    print("\n=== MID-CAP by year (vs SPY, 63d) ===")
    print(table(mid, "abspy_63", "year"))
    print("\n=== MID-CAP horizon decay (vs SPY) ===")
    for h in HORIZONS:
        print(table(mid, f"abspy_{h}").rename(index={"ALL": f"{h}d"}))
    print("\n=== MID-CAP: standalone 8.01 announcement vs earnings-bundled ===")
    print(table(mid, "abspy_63", "pure_801"))

    x = mid["abspy_63"].dropna()
    mean, t = x.mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    recent = mid[mid["year"] >= 2024]["abspy_63"].dropna().mean()
    print(f"\nMid-cap N={len(x)} mean={mean:+.2%} t={t:.2f} 2024+mean={recent:+.2%}")
    print("NOTE: overlapping windows + event clustering inflate t; treat as upper bound.")
    if mean >= 0.012 and t >= 1.5 and recent >= 0:
        print("VERDICT: GO — build the EDGAR sleeve harness.")
    elif mean < 0.005 or t < 1.0:
        print("VERDICT: KILL — drift not present in our sample.")
    else:
        print("VERDICT: MARGINAL — decide with eyes open.")


if __name__ == "__main__":
    main()
