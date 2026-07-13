"""Spinoff drift — 1-day kill test (POC).

Event stream #3 of the A5-Events candidate pool (AUDIT_FABLE §5.1).
Thesis (Greenblatt; McConnell-Ovtchinnikov): index funds and parent-holder
mandates dump newly distributed spinco shares mechanically in the first
weeks; the spinco then outperforms for months.

Harvest: EDGAR full-text search, forms=10-12B (exchange registration —
filed by the spinco itself), q="spin-off", 2021-H2..2026-Q1. Ticker comes
from EDGAR's current company record in display_names (assigned once
listed). Registrants that never listed have no ticker -> excluded and
counted (survivorship: removes failed spinoffs, biases GO upward).

Event clock: t0 = spinco's first yfinance price bar. Sanity guard: t0 must
fall within [file_date - 30d, file_date + 400d]; tickers with long price
history predating the registration are EDGAR mis-maps or non-spinoff
reorganizations -> excluded.

Entries: T+1 after first bar ("day one") and T+21 ("post-dump"). Hold 63
trading days. Abnormal vs SPY and MDY. Verdict keyed on the T+21 entry.

Kill criteria (fixed before first run):
  KILL      T+21 mean 63d abnormal vs MDY < +1.0% or t < 1.0
  GO        T+21 mean >= +2.5%, t >= 1.5, 2024+ mean >= 0
  MARGINAL  between

Usage: uv run python3 scripts/spinoff_drift_poc.py [--refresh]
"""

import argparse
import os
import re
import time

import numpy as np
import pandas as pd
import requests

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "research_cache")
EVENTS_CSV = os.path.join(CACHE_DIR, "spinoff_events.csv")
PRICES_PQ = os.path.join(CACHE_DIR, "spinoff_prices.parquet")

FTS_URL = "https://efts.sec.gov/LATEST/search-index"
UA = {"User-Agent": "George Borshukov gdborshukov@gmail.com (FIRE research)"}
TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,9})(?:,[^)]*)?\)\s+\(CIK")
BENCH = ["SPY", "MDY"]
HOLD = 63
ENTRIES = {"day1": 1, "post_dump": 21}
WINDOWS = [
    ("2021-07-01", "2021-12-31"), ("2022-01-01", "2022-06-30"),
    ("2022-07-01", "2022-12-31"), ("2023-01-01", "2023-06-30"),
    ("2023-07-01", "2023-12-31"), ("2024-01-01", "2024-06-30"),
    ("2024-07-01", "2024-12-31"), ("2025-01-01", "2025-06-30"),
    ("2025-07-01", "2025-12-31"), ("2026-01-01", "2026-03-31"),
]
MAX_PAGES = 15


def harvest_events() -> pd.DataFrame:
    rows = []
    for start, end in WINDOWS:
        for page in range(MAX_PAGES):
            params = {"q": '"spin-off"', "forms": "10-12B", "startdt": start, "enddt": end}
            if page:
                params["from"] = page * 10
            r = requests.get(FTS_URL, params=params, headers=UA, timeout=30)
            if r.status_code != 200:
                print(f"  FTS {r.status_code} on {start} p{page}")
                break
            hits = r.json().get("hits", {}).get("hits", [])
            for h in hits:
                src = h["_source"]
                name = (src.get("display_names") or [""])[0]
                m = TICKER_RE.search(name)
                rows.append(
                    {
                        "cik": (src.get("ciks") or [""])[0],
                        "ticker": m.group(1).replace(".", "-") if m else None,
                        "file_date": src["file_date"],
                        "company": name.split("  (")[0],
                    }
                )
            time.sleep(0.12)
            if len(hits) < 10:
                break
        print(f"  through {end}: {len(rows)} raw hits")
    df = pd.DataFrame(rows)
    df["file_date"] = pd.to_datetime(df["file_date"])
    # one row per registrant: earliest filing (amendments repeat the CIK)
    df = df.sort_values("file_date").groupby("cik", as_index=False).first()
    return df


def fetch_prices(tickers: list[str]) -> pd.DataFrame:
    import yfinance as yf

    todo = sorted(set(tickers) | set(BENCH))
    frames = []
    for i in range(0, len(todo), 100):
        chunk = todo[i : i + 100]
        px = yf.download(chunk, start="2021-01-01", progress=False, auto_adjust=True)["Close"]
        if isinstance(px, pd.Series):
            px = px.to_frame(chunk[0])
        frames.append(px)
    out = pd.concat(frames, axis=1)
    out = out.loc[:, ~out.columns.duplicated()]
    out.index = pd.to_datetime(out.index)
    return out


def event_study(events: pd.DataFrame, px: pd.DataFrame) -> pd.DataFrame:
    idx = px.index
    recs = []
    for _, ev in events.iterrows():
        t = ev["ticker"]
        if not t or t not in px.columns:
            recs.append({**ev, "status": "no_ticker_or_prices"})
            continue
        s = px[t].dropna()
        if s.empty:
            recs.append({**ev, "status": "no_ticker_or_prices"})
            continue
        first_bar = s.index[0]
        lag = (first_bar - ev["file_date"]).days
        if lag < -30 or lag > 400:
            recs.append({**ev, "status": "not_new_listing", "first_bar": first_bar})
            continue
        rec = {**ev, "status": "ok", "first_bar": first_bar, "days_reg_to_list": lag}
        t0 = idx.searchsorted(first_bar)
        for tag, elag in ENTRIES.items():
            ep = t0 + elag
            xp = ep + HOLD
            if xp >= len(idx):
                rec[f"{tag}_ret"] = np.nan
                continue
            eday, xday = idx[ep], idx[xp]
            if eday not in s.index or xday not in s.index:
                rec[f"{tag}_ret"] = np.nan
                continue
            r = s[xday] / s[eday] - 1
            rec[f"{tag}_ret"] = r
            for b in BENCH:
                br = px[b][xday] / px[b][eday] - 1
                rec[f"{tag}_ab{b.lower()}"] = r - br
        recs.append(rec)
    return pd.DataFrame(recs)


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
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    os.makedirs(CACHE_DIR, exist_ok=True)

    if args.refresh or not os.path.exists(EVENTS_CSV):
        print("Harvesting EDGAR 10-12B registrations…")
        harvest_events().to_csv(EVENTS_CSV, index=False)
    events = pd.read_csv(EVENTS_CSV, parse_dates=["file_date"])
    with_t = events.dropna(subset=["ticker"])
    print(f"Registrants: {len(events)} | with ticker: {len(with_t)} "
          f"(no ticker = never listed / not in EDGAR map: {len(events) - len(with_t)})")

    if args.refresh or not os.path.exists(PRICES_PQ):
        print("Fetching prices…")
        fetch_prices(with_t["ticker"].tolist()).to_parquet(PRICES_PQ)
    px = pd.read_parquet(PRICES_PQ)

    res = event_study(events, px)
    ok = res[res["status"] == "ok"].copy()
    print(f"Usable: {len(ok)} | not_new_listing (EDGAR mis-map/reorg): "
          f"{(res['status'] == 'not_new_listing').sum()} | "
          f"no ticker/prices: {(res['status'] == 'no_ticker_or_prices').sum()}")
    ok["year"] = pd.to_datetime(ok["first_bar"]).dt.year

    for tag in ENTRIES:
        print(f"\n=== entry {tag}, {HOLD}d hold ===")
        for b in ["abspy", "abmdy"]:
            print(table(ok, f"{tag}_{b}").rename(index={"ALL": f"vs {b[2:].upper()}"}))
    print("\n=== post_dump entry by listing year (vs MDY) ===")
    print(table(ok, "post_dump_abmdy", "year"))

    x = ok["post_dump_abmdy"].dropna()
    if len(x) < 10:
        print(f"\nN={len(x)} — too thin to verdict; harvest more windows.")
        return
    mean, t = x.mean(), x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    recent = ok[ok["year"] >= 2024]["post_dump_abmdy"].dropna().mean()
    print(f"\nN={len(x)} post_dump mean(abMDY)={mean:+.2%} t={t:.2f} 2024+mean={recent:+.2%}")
    print("NOTE: never-listed registrants excluded (survivorship, favors GO); "
          "KILL is conservative.")
    if mean >= 0.025 and t >= 1.5 and recent >= 0:
        print("VERDICT: GO — spinoff stream earns a slot in the A5-Events pool.")
    elif mean < 0.01 or t < 1.0:
        print("VERDICT: KILL — no exploitable post-distribution drift in our sample.")
    else:
        print("VERDICT: MARGINAL — decide with eyes open.")


if __name__ == "__main__":
    main()
